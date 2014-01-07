'''
Created on 13-Aug-2013

@author: someshs
'''
import sys
from datetime import datetime
from tornado.web import HTTPError
from requires.base import BaseHandler, authenticated
from datamodels.organization import Organization, OrganizationProfile
from datamodels.permission import OrganizationPermission
from datamodels.user import User
from mongoengine.errors import ValidationError
from utils.dumpers import json_dumper
from requires.settings import organization_permission_map

sys.dont_write_bytecode = True

class OrganizationHandler(BaseHandler):
    SUPPORTED_METHODS = ('GET', 'POST', 'PUT', 'DELETE')
    REQUIRED_FIELDS   = {
        'PUT': ('name',),
        }
    data = {}

    def __init__(self, *args, **kwargs):
        super(OrganizationHandler, self).__init__(*args, **kwargs)

    def clean_request(self):
        print self.data
        self.data.update({'created_by': self.current_user,
                         'updated_by': self.current_user,
                         'admin': self.current_user})

    def validate_request(self, organization):
        if not organization:
            self.send_error(400)
        else:
            try:
                org = Organization.get_organization_object(organization)
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
            return org

    @authenticated
    def get(self, *args, **kwargs):
        organization  = kwargs.get('organization', None)
        org = self.validate_request(organization)
        if org not in self.current_user.belongs_to:
            self.send_error(404)
        self.write(org.to_json())

    @authenticated
    def post(self, *args, **kwargs):
        pass
#        organization  = kwargs.get('organization', None)
#        response = {}
#        org = self.validate_request(organization)
#        if not org:
#            self.send_error(404)
#        else:
#            OrganizationProfile(**self.data)

    def set_org_permission(self, org=None, role=None):
        p = OrganizationPermission(organization=org,
                          user=self.current_user,
                          map=organization_permission_map[role])
        p.save()

    @authenticated
    def put(self, *args, **kwargs):
        self.clean_request()
        print somesh
        org = Organization(**self.data)
        try:
            org.save(validate=True, clean=True)
            self.current_user.update_organization_list(org)
            self.write(org.to_json())
            self.set_org_permission(org=None, role='super_admin')
            OrganizationProfile.objects.create(organization=org,
                                               created_by=self.current_user,
                                               updated_by=self.current_user)
        except ValidationError, error:
            raise HTTPError(403, **{'reason':self.error_message(error)})

    @authenticated
    def delete(self, *args, **kwargs):
        organization  = kwargs.get('organization', None)
        org = self.validate_request(organization)
        members = [user for user in User.objects if org in user.belongs_to]
        [member.belongs_to.pop(member.belongs_to.index(org)) for
         member in members]
        org.delete()
        self.write({'message': 'Deleted Successfully.'})


class OrgProfileHandler(BaseHandler):
    SUPPORTED_METHODS = ('GET', 'POST', 'PUT', 'DELETE')
    REQUIRED_FIELDS   = {
        'PUT': ('display_name', 'url', 'location'),
        'DELETE' : ('id',),
        }
    data = {}

    def __init__(self, *args, **kwargs):
        super(OrgProfileHandler, self).__init__(*args, **kwargs)

    def clean_request(self, org):
        self.data.update({'created_by': self.current_user,
                         'updated_by': self.current_user,
                         'organization': org})


    def validate_request(self, organization):
        if not organization:
            self.send_error(400)
        else:
            try:
                org = Organization.get_organization_object(organization)
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
            return org

    @authenticated
    def get(self, *args, **kwargs):
        organization  = kwargs.get('organization', None)
        response = {}
        org = self.validate_request(organization)
        if not org:
            self.send_error(404)
        else:
            response['organization'] = org.to_json()
            response['organization_profile'] = json_dumper(
                                               org.get_organization_profile())
            self.write(response)

    @authenticated
    def post(self, *args, **kwargs):
        organization  = kwargs.get('organization', None)
        org = self.validate_request(organization)
        if not org:
            self.send_error(404)
        else:
            org_profile = org.get_organization_profile()
            temp_data = {'set__'+field: self.data[field] for field 
                         in OrganizationProfile._fields.keys() 
                         if field in self.data.keys()}
            temp_data.update({'set__updated_by': self.current_user,
                              'set__updated_at': datetime.utcnow()})
            org_profile.update(**temp_data)
            self.write(org_profile.to_json())

    @authenticated
    def put(self, *args, **kwargs):
        organization  = kwargs.get('organization', None)
        org = self.validate_request(organization)
        if not org:
            self.send_error(404)
        else:
            self.clean_request(org)
            org_profile = OrganizationProfile(**self.data)
            try:
                org_profile.save()
                self.write(org_profile.to_json())
            except ValidationError, error:
                raise HTTPError(403, **{'reason':self.error_message(error)})

    @authenticated
    def delete(self, *args, **kwargs):
        organization  = kwargs.get('organization', None)
        org = self.validate_request(organization)
        if not org:
            self.send_error(404)
        else:
            org.get_organization_profile().delete()
            self.write({'message': 'Deleted Successfully.'})
