import sys
sys.dont_write_bytecode = True
import re
import mongoengine as me
from mongoengine.base import ValidationError

from organization import Organization
from userprofile import UserProfile
from utils.dumpers import  json_dumper
from requires.settings import SETTINGS
from utils import QueryObject
import string
import random
from datetime import datetime as dt, timedelta as td

sys.dont_write_bytecode = True

USERNAME_REGX = re.compile('[a-zA-Z0-9-_\.]*$')
EMAIL_REGX = re.compile('[a-zA-Z0-9_.-@]*$')


def generate_token():
    """Random string generator method for Reset password token"""
    return "".join([random.choice(
        string.ascii_letters + string.hexdigits)
        for n in xrange(30)])


class User(me.Document):
    username = me.StringField(max_length=32,
                              unique=True, required=True)
    password = me.StringField(required=True)
    email = me.EmailField(required=True, unique=True)
    # Profile
    profile = me.ReferenceField('UserProfile', dbref=True)
    # Org
    belongs_to = me.ListField(me.ReferenceField('Organization'))
    roles = me.DictField(default={})

    meta = {
        "indexes": ["username", "email"]
    }

    def __str__(self):
        return unicode(self.username)

    @property
    def user_role(self, project_name=None):
        """
        Returns role object for user in a specified project scope
        :param project_name: Project name to scope role
        :type project_name: str
        :return: Role / None
        """
        permalink = "%s/%s" % (self.username, project_name)
        if not project_name or not self.roles.get(permalink):
            return None
        project = QueryObject(None, 'Project', {
            'permalink': permalink})
        if not project.count == 1:
            return None
        project = project.result[0]
        role = QueryObject(None, 'Role', {
            'project': project,
            'role': self.roles.get(permalink)})
        return role[0] if role.count == 1 else None


    def to_json(self, fields=None, exclude=None):
        return json_dumper(self, fields, exclude)

    def clean(self):
        if len(User.objects.filter(username=self.username)) > 0:
            raise ValidationError('Username already exists')
        if len(User.objects.filter(email=self.email)) > 0:
            raise ValidationError('Email already exists')
        if USERNAME_REGX is not None and USERNAME_REGX.match(
                 self.username) is None:
            raise ValidationError('Special characters not allowed in username.')

    def update_profile(self, _oauth=None, _provider=None):
        data_dict = {}
        if _oauth and isinstance(_oauth, dict):
            _oauth_dict = {}
            _oauth_dict = {_provider: _oauth}
            data_dict.update({_provider: _oauth})
        data_dict['created_by'] = self
        data_dict['updated_by'] = self
        data_dict['avatar'] = SETTINGS['default_avatar']
        user_profile = UserProfile(**data_dict)
        user_profile.save()
        self.update(set__profile=user_profile)

    def update_organization_list(self, organization=None):
        if not self.belongs_to:
            self.update(set__belongs_to=[organization])
        else:
            self.belongs_to.append(organization)
            self.update(set__belongs_to=self.belongs_to)

    def get_user_profile(self):
        return UserProfile.objects.filter(user=self)

    def save(self, *args, **kwargs):
        super(User, self).save(*args, **kwargs)
        self.reload()

    def update(self, *args, **kwargs):
        super(User, self).update(*args, **kwargs)
        self.reload()


class PasswordResetToken(me.Document):
    """
    Password reset token document. Takes in a user reference
    generated from the API PUT handler for password reset and sets
    a 24 hour validity timestamp for the token.
    #todo: Initiate email from here
    """

    token = me.StringField()
    user = me.ReferenceField('User', unique=True)
    created = me.DateTimeField(default=dt.utcnow())
    valid_until = me.DateTimeField(default=None)

    def reset_token(self, *args, **kwargs):
        """
        PasswordResetToken update method.
        Updates created, token, and validity stamps if an existing
        object is found in the collection and user attempts reset
        again.
        """
        setattr(self, 'created', dt.utcnow())
        setattr(self, 'token', generate_token())
        setattr(self, 'valid_until', self.created + td(days=1))
        super(PasswordResetToken, self).save()

    def save(self, *args, **kwargs):
        if self.token:
            raise ValidationError(
                "Token needs to be generated on save")

        if self.valid_until:
            raise ValidationError(
                "Validity needs to be generated on save")

        self.token = generate_token()
        self.valid_until = self.created + td(days=1)

        super(PasswordResetToken, self).save(*args, **kwargs)


if __name__ == '__main__':
    pass

