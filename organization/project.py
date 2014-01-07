'''
Created on 14-Aug-2013

@author: someshs
'''
import sys
from tornado.web import HTTPError
from requires.base import BaseHandler, authenticated
from datamodels.organization import Organization
from datamodels.project import Project
from datamodels.permission import ProjectPermission
from mongoengine.errors import ValidationError
from utils.app import millisecondToDatetime
from utils.dumpers import json_dumper
import json

sys.dont_write_bytecode = True

class OrgProjectHandler(BaseHandler):
    SUPPORTED_METHODS = ('GET', 'POST', 'DELETE', 'PUT')
    REQUIRED_FIELDS = {'PUT': ('title',)}
    data = {}

    def clean_request(self, organization):
        if not organization:
            self.send_error(404)
        else:
            try:
                org = Organization.get_organization_object(organization)
                self.data['organization'] = org
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
        
        [self.data.pop(key) for key in self.data.keys()
         if key not in Project._fields.keys()]
        for k in ['start_date', 'end_date']:
            self.data[k] = millisecondToDatetime(self.data[k])
        self.data['duration'] = int(self.data['duration'])
        if self.request.method == 'PUT':
            self.data['created_by'] = self.current_user
        self.data['updated_by'] = self.current_user

    def validate_request(self, organization):
        if not organization:
            self.send_error(400)
        else:
            try:
                org = Organization.get_organization_object(organization)
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
            return org


    def set_user_permission(self, project):
        p = ProjectPermission(project=project,
                          user=self.current_user,
                          map=2047)
        p.save()

    @authenticated
    def get(self, *args, **kwargs):
        organization = kwargs.get('organization', None)
        org = self.validate_request(organization)
        response = None
        sequence = self.get_argument('projectId', None)
        owner = self.get_argument('owner', None)
        project_name = self.get_argument('project_name', None)
        
        # By Sequence number
        if sequence:
            try:
                project = Project.get_project_object(sequence=sequence,
                                                     organization=org)
                if self.current_user in project.members:
                    response['project'] = project.to_json()
                    response['project'].update({
                        'current_sprint' : project.get_current_sprint().to_json()
                    })
                else:
                    raise HTTPError(404, **{'reason': "Project Not found."})
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
        
        # By permalink
        elif owner and project_name:
            permalink = owner + '/' + project_name
            try:
                project = Project.objects.get(
                            permalink__iexact=permalink,
                            members=self.current_user,
                            organization=org,
                            is_active=True
                        )
                if not project:
                    raise HTTPError(404)
                
                if not self.current_user in project.members:
                    raise HTTPError(403)
            
                response['project'] = project.to_json()
                response['project'].update({
                    'current_sprint' : project.get_current_sprint().to_json()
                })
            except Project.DoesNotExist:
                raise HTTPError(404)
        else:
            # Check if we are returning a list of projects for
            # the logged in user
            projects = Project.objects(members=self.current_user,
                                       organization=org
                                       ).order_by('created_on')
            response['projects'] = []
            for p in projects:
                response['projects'].append(p.to_json())
                response['projects'][-1].update({
                    'current_sprint': p.get_current_sprint().to_json()
                })
        
        self.finish(json.dumps(response))


        if not self._headers_written:
            self.write(json.dumps(response))
    
    @authenticated
    def put (self, *args, **kwargs):
        organization = kwargs.get('organization', None)
        org = self.validate_request(organization)
        self.clean_request(organization)
        project = Project(**self.data)
        try:
            project.save(validate=True, clean=True)
            self.set_user_permission(project)
        except ValidationError, error:
            raise HTTPError(500, **{'reason':self.error_message(error)})
        
        if not self._headers_written:
            self.write(project.to_json())


class SprintHandler(BaseHandler):
    
    SUPPORTED_METHODS = ('GET', 'PUT')
    REQUIRED_FIELDS   = {
        'PUT': ('projectId','sprints'),
        'GET': ('projectId',)
        }
    data = {}
    
    def get_valid_project(self, project_id, organization):
        if not project_id:
            self.send_error(404)
        try:
            project = Project.get_project_object(sequence=project_id,
                                                 organization=organization)
            if self.current_user != project.admin:
                self.send_error(404)
        except ValidationError, error:
            raise HTTPError(404, **{'reason': self.error_message(error)})
        return project

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
    def get(self,*args, **kwargs):
        organization = kwargs.get('organization', None)
        org = self.validate_request(organization)
        project_id = self.get_argument('projectId', None)
        sprint_sequence = self.get_argument('sprint',None)
        response = {}
        project = self.get_valid_project(project_id, org)
        if not sprint_sequence:
            sprints = list(Sprint.objects.filter(project=project))
            response['sprints'] = json_dumper(sprints)
        elif sprint_sequence:
            try:
                sprint = project.get_sprint_object(sprint_sequence)
                response['sprint'] = sprint.to_json()
                response['stories'] = json_dumper(list(sprint.get_stories()))
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
        response['project'] = project.to_json()
        self.finish(json.dumps(response))

    @authenticated
    def put(self, *args, **kwargs):
        organization = kwargs.get('organization', None)
        org = self.validate_request(organization)
        project_id = self.data.get('projectId', None)
        number_of_sprints = self.data.get('sprints', None)
        project = self.get_valid_project(project_id, org)
        response = {}
        for each in xrange(number_of_sprints):
            try:
                sprint = project.add_sprint(self.current_user)
                response['Sprint :' + str(sprint.sequence)] = sprint.to_json()
            except ValidationError, error:
                raise HTTPError(500, **{'reason':self.error_message(error)})
        self.write(response)


