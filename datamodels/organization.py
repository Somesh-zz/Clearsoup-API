'''
Created on 12-Aug-2013

@author: someshs
'''
import sys
sys.dont_write_bytecode = True
from datetime import datetime

from mongoengine.base import ValidationError
from mongoengine import signals
import mongoengine as me
from utils.dumpers import json_dumper
NAME_REGX = '^[a-zA-Z0-9_\s]*$'


class Organization(me.Document):
    name = me.StringField(required=True, max_length=30, unique=True,
                          regex=NAME_REGX)
    admin = me.ReferenceField('User', dbref=True)
    owners = me.ListField(me.ReferenceField('User', dbref=True))

    created_at = me.DateTimeField(default=datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.utcnow)
    created_by = me.ReferenceField('User', required=False, dbref=True)
    updated_by = me.ReferenceField('User', required=False, dbref=True)
    is_active = me.BooleanField(default=True)

    meta = {
        'indexes': ['name']
        }
    def __str__(self):
        return self.name

    def clean(self):
        if Organization.objects.filter(name=self.name).count() > 0:
            raise ValidationError('Duplicate Organization')
        if len(self.name) > 30:
            raise ValidationError('Maximum 30 characters allowed')

    @classmethod
    def post_save(cls,  sender, document, **kwargs):
        if document.admin not in document.owners:
            document.owners.append(document.admin)
            document.update(set__owners=document.owners)

    def save(self, *args, **kwargs):
        super(Organization, self).save(*args, **kwargs)
        self.reload()

    def update(self, *args, **kwargs):
        super(Organization, self).update(*args, **kwargs)
        self.reload()

    @classmethod
    def get_organization_object(cls, name):
        try:
            org = Organization.objects.get(name=name)
        except Organization.DoesNotExist, error:
            raise ValidationError(error.message)
        return org


    def get_organization_profile(self):
        org_profile = OrganizationProfile.objects.filter(organization=self)
        if org_profile:
            org_profile = org_profile[0]
        else:
            org_profile = []
        return org_profile

    def to_json(self, fields=None, exclude=None):
        return json_dumper(self, fields, exclude)


class OrganizationProfile(me.Document):
    display_name = me.StringField(max_length=64, default=None)
    organization = me.ReferenceField('Organization', required=True,
                                     unique=True, reverse_delete_rule=True)
    url = me.URLField()
    location = me.StringField()
    logo = me.URLField()
    contact_number = me.StringField()
    
    created_at = me.DateTimeField(default=datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.utcnow)
    created_by = me.ReferenceField('User', required=False)
    updated_by = me.ReferenceField('User', required=False)
    is_active = me.BooleanField(default=True)

    meta = {
        'indexes': ['organization']
        }

    def __str__(self):
        return str(self.organization)
    
    def save(self, *args, **kwargs):
        super(OrganizationProfile, self).save(*args, **kwargs)
        self.reload()

    def update(self, *args, **kwargs):
        super(OrganizationProfile, self).update(*args, **kwargs)
        self.reload()

    def to_json(self, fields=None, exclude=None):
        return json_dumper(self, fields, exclude)


signals.post_save.connect(Organization.post_save, sender=Organization)
