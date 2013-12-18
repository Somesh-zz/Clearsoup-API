import sys
from bson.json_util import default
sys.dont_write_bytecode = True

import mongoengine as me
import re

from mongoengine.base import ValidationError
from mongoengine import signals
from datetime import datetime
from utils.dumpers import json_dumper
import logging
from utils import QueryObject

from datamodels.notification import NotificationManager
from websocket.handlers import send_notifications
from requires.settings import TEAM_ROLES, ADMIN_ROLES

MENTION_REGEX = r'@[A-Za-z0-9_.-]+'
HASHTAG_REGEX = r'#[A-Za-z0-9_.-]+'
UPDATE_REGEX = '^[a-zA-Z0-9-_,;.\?\/\s]*$'

update_model_logger = logging.getLogger(__name__)

__all__ = ('Update', 'TaskUpdate',)


class SendUpdateNotification:
    @staticmethod
    def send_update_notification(document):
        if document.mentions:
            # A user can be mentioned more than once in the same
            # message, which is unnecessary repetition. Filter out
            # the unique
            mentions = set(document.mentions)
            if 'all' in mentions:
                mentions = [user.username for user
                            in document.project.members]
            else:
                roles = ADMIN_ROLES + TEAM_ROLES

                role_mentions = [role for role in mentions
                                 if role in document.project.roles]

                user_mentions = [mention for mention in mentions if
                                 mention not in role_mentions]

                users = QueryObject(None, 'User', {'username__in':
                                               user_mentions})

                users = [user.username for user in
                         users.result if getattr(user, 'roles',
                        {}).get(document.project.permalink) not in
                                         role_mentions]

                mentions = users + role_mentions

            notifications = {}
            for mentioned_user in mentions:
                try:
                    notification = NotificationManager.createNotification(
                        for_user=mentioned_user,
                        from_user=document.created_by,
                        notification_type='M',
                        text=document.text
                        )
                    notifications[mentioned_user] = notification
                except ValidationError: pass
            # Now publish the notification to the websocket
            try:
                send_notifications(notifications)
            except: pass


class Update(me.Document):
    # Meta
    created_by = me.ReferenceField('User', required=True, dbref=True)
    created_at = me.DateTimeField(default=datetime.utcnow())

    # Fields
    project = me.ReferenceField('Project', required=True, dbref=True, 
                                reverse_delete_rule=me.CASCADE)
    text = me.StringField(max_length=140, required=True)
    mentions = me.ListField(required=False)
    hashtags = me.ListField(required=False)

    def to_json(self, fields=None, exclude=None):
        return json_dumper(self, fields, exclude)

    @classmethod
    def pre_save(cls, sender, document, **kwargs):
        '''
            validating max length and mentioned user
        '''
        mentions = re.findall(MENTION_REGEX, document.text)
        if len(mentions) > 0:
            document.mentions = [mention[1:] for mention in mentions]
        if document.created_by not in document.project.members:
            raise ValidationError('You are not a member of this project')
        if len(document.text) > 140:
            raise ValidationError('Update exceeds 140 characters')


    @classmethod
    def post_save(cls, sender, document, **kwargs):
        SendUpdateNotification.send_update_notification(document)

    def save(self, *args, **kwargs):
        # Explicitly set the date as mongo(engine|db) seems to
        # cache the date
        self.created_at = datetime.utcnow()
        # Extract list of mentions and hashtags
        # and save it
        mentions = re.findall(MENTION_REGEX, self.text)
        if len(mentions) > 0:
            self.mentions = [mention[1:] for mention in mentions]
        hashtags = re.findall(HASHTAG_REGEX, self.text)
        if len(hashtags) > 0:
            self.hashtags = [hashtag[1:] for hashtag in hashtags]
            self.project.hashtags.extend(self.hashtags)
            self.project.update(set__hashtags=set(self.project.hashtags))
        super(Update, self).save(*args, **kwargs)


class TaskUpdate(me.Document):
    # Meta
    created_by = me.ReferenceField('User', required=True, dbref=True)
    created_at = me.DateTimeField(default=datetime.utcnow())
    updated_by = me.ReferenceField('User', required=True, dbref=True)
    # Fields
    project = me.ReferenceField('Project', required=True)
    task = me.ReferenceField('Task', required=True)
    text = me.StringField(max_length=140, required=True)
    is_active = me.BooleanField(default=True)
    mentions = me.ListField(required=False)
    hashtags = me.ListField(required=False)


    @classmethod
    def pre_save(cls, sender, document, **kwargs):
        '''
            validating max length and mentioned user
        '''
        mentions = re.findall(MENTION_REGEX, document.text)
        if len(mentions) > 0:
            document.mentions = [mention[1:] for mention in mentions]
        if document.created_by not in document.project.members:
            raise ValidationError('You are not a member of this project')
        if len(document.text) > 140:
            raise ValidationError('Update exceeds 140 characters')

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        SendUpdateNotification.send_update_notification(document)
    
    def save(self, *args, **kwargs):
        # Explicitly set the date as mongo(engine|db) seems to
        # cache the date
        self.created_at = datetime.utcnow()
        # Extract list of mentions and hashtags
        # and save it
        mentions = re.findall(MENTION_REGEX, self.text)
        if len(mentions) > 0:
            self.mentions = [mention[1:] for mention in mentions]
        hashtags = re.findall(HASHTAG_REGEX, self.text)
        if len(hashtags) > 0:
            self.hashtags = [hashtag[1:] for hashtag in hashtags]
            self.project.hashtags.extend(self.hashtags)
            self.project.update(set__hashtags=set(self.project.hashtags))
        super(TaskUpdate, self).save(*args, **kwargs)
        self.reload()

    def to_json(self, fields=None, exclude=None):
        return json_dumper(self, fields, exclude)

signals.pre_save.connect(Update.pre_save, sender=Update)
signals.pre_save.connect(TaskUpdate.pre_save, sender=Update)

# Post save for update to create the necessary notifications
# for the user(s) mentioned in the update
signals.post_save.connect(Update.post_save, sender=Update)
signals.post_save.connect(TaskUpdate.post_save, sender=TaskUpdate)
