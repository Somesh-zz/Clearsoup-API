'''
Created on 06-Aug-2013

@author: someshs
'''
import json
from tornado.web import HTTPError
from mongoengine import ValidationError, Q

from requires.base import BaseHandler, authenticated, validate_path_arg
from datamodels.analytics import ProjectMetadata
from datamodels.project import Project, Sprint
#from datamodels.group import Group
from datamodels.organization import Organization
from datamodels.story import Story
from datamodels.team import Team
from datamodels.user import User
from datamodels.permission import Role
from utils.app import millisecondToDatetime
from utils.dumpers import json_dumper
from requires.settings import PROJECT_PERMISSIONS, permission_map, \
    TEAM_ROLES


class ProjectHandler(BaseHandler):
    
    SUPPORTED_METHODS = ('GET', 'POST', 'PUT', 'DELETE')
    REQUIRED_FIELDS   = {
        'POST': ('projectId',),
        'PUT': ('title','start_date', 'end_date'),
        'DELETE' : ('projectId',),
        }
    data = {}
    
    def clean_request(self):
        '''
            function to remove additional data key send in request.
            e.g token
            
            Besides above, it also cleans the date-time values and duration
        '''
        [self.data.pop(key) for key in self.data.keys()
         if key not in Project._fields.keys()]
        for k in ['start_date', 'end_date']:
            self.data[k] = millisecondToDatetime(self.data[k])
        self.data['duration'] = int(self.data['duration'])
        if self.request.method == 'PUT':
            self.data['created_by'] = self.current_user
        self.data['updated_by'] = self.current_user


    @authenticated
    def get(self, *args, **kwargs):
        """
        Get a list of projects by passing in:
        1) projectId - the project sequence number (returns a single project)
        2) owner and project_name - Gets the project in either 
        the user or org context
        3) No params - List all the projects for the current authenticated user
        """
        sequence = self.get_argument('projectId', None)
        owner = self.get_argument('owner', None)
        project_name = self.get_argument('project_name', None)
        response = {}
        # By Sequence number
        if sequence:
            try:
                project = Project.get_project_object(sequence)
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
                            members=self.current_user
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

        # All projects for the current
        else:
            # Check if we are returning a list of projects for
            # the logged in user
            projects = Project.objects(members=self.current_user
                                       ).order_by('created_on')
            response['projects'] = []
            for p in projects:                
                response['projects'].append(p.to_json())
                response['projects'][-1].update({
                    'current_sprint': p.get_current_sprint().to_json()
                })
        
        self.finish(json.dumps(response))

    def get_valid_project(self, project_id=None, permalink=None):
        if not project_id and not permalink:
            self.send_error(404)
        if project_id:
            try:
                project = Project.get_project_object(sequence=project_id)
                if self.current_user not in project.members:
                    self.send_error(404)
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
        elif permalink:
            try:
                project = Project.objects.get(
                            permalink__iexact=permalink,
                        )
                if not self.current_user in project.members:
                    raise HTTPError(403)
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
        return project

    @authenticated
    def post(self, *args, **kwargs):
        project_id = self.get_argument('projectId', None)
        owner = self.get_argument('owner', None)
        project_name = self.get_argument('project_name', None)
        project_permalink = self.get_argument('project_pemalink', None)
        roles = self.get_arguments('roles', None)
        extended_date = self.get_argument('extended_date', None)
        project = None

        if project_id:
            project = self.get_valid_project(project_id)
        elif owner and project_name:
            permalink = owner + '/' + project_name
            project = self.get_valid_project(project_id, permalink)
        elif project_permalink:
            project = self.get_valid_project(project_id=None,
                                             permalink=project_permalink)
        else:
            self.send_error(400)
        if roles:
            new_roles = [role for role in roles if role not in project.roles]
            Role.create_role_map(new_roles, project, self.current_user,
                                 map=0)
            project.roles.extend(roles)
            project.update(set__roles=set(list(project.roles)))
        if extended_date and project.is_todo:
            extended_date = millisecondToDatetime(extended_date)
            project.update(set__end_date=extended_date)
        self.write(project.to_json())

    def create_role(self, project, creating_project):
        if creating_project:
            for role in project.roles:
                r = Role(project=project,
                        role=role,
                        map=permission_map[role],
                        created_by=self.current_user,
                        updated_by=self.current_user)
                r.save()
        else:
            pass

    @authenticated
    def put(self, *args, **kwargs):
        self.clean_request()
        project = Project(**self.data)
        try:
            project.save(validate=True, clean=True)
            ProjectMetadata.create_project_metadata(project)
            Story.create_todo(project, self.current_user)
            self.create_role(project, creating_project=True)
            Team.create_team(project=project, user=self.current_user)
        except ValidationError, error:
            raise HTTPError(500, **{'reason':self.error_message(error)})
        self.write(project.to_json())

    @authenticated
    def delete(self, *args, **kwargs):
        sequence = self.get_argument('projectId', None)
        try:
            project = Project.get_project_object(sequence)
            project.update(set__active=False)
            self.write(project.to_json())
        except ValidationError, error:
            raise HTTPError(404, **{'reason': self.error_message(error)})


class ProjectSettingHandler(BaseHandler):
    
    SUPPORTED_METHODS = ('GET',)
    REQUIRED_FIELDS   = {
        }
    data = {}
    
    def get_valid_project(self, project_id=None, permalink=None):
        if not project_id and not permalink:
            self.send_error(404)
        if project_id:
            try:
                project = Project.get_project_object(sequence=project_id)
                if self.current_user not in project.members:
                    self.send_error(404)
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
        elif permalink:
            try:
                project = Project.objects.get(
                            permalink__iexact=permalink,
                        )
                if not self.current_user in project.members:
                    raise HTTPError(403)
            except ValidationError, error:
                raise HTTPError(404, **{'reason': self.error_message(error)})
        return project

    def generate_readable_permission_json(self, group=None):
        permission_dict = {}
        for perm in PROJECT_PERMISSIONS:
            if Role.testBit(group.map,
                             PROJECT_PERMISSIONS.index(perm)):
                permission_dict[perm] = 1
            else:
                permission_dict[perm] = 0
        return permission_dict

    @authenticated
    def get(self, *args, **kwargs):
        project_id = self.get_argument('projectId', None)
        owner = self.get_argument('owner', None)
        project_name = self.get_argument('project_name', None)
        project_permalink = self.get_argument('project_pemalink', None)
        project = None
        response = {}
        if project_id:
            project = self.get_valid_project(project_id)
        elif owner and project_name:
            permalink = owner + '/' + project_name
            project = self.get_valid_project(project_id, permalink)
        elif project_permalink:
            project = self.get_valid_project(project_id=None,
                                             permalink=project_permalink)
        else:
            self.send_error(400)
        roles = Role.objects.filter(project=project
                                           ).exclude('created_by', 'updated_by',
                                                     'project', 'updated_on', 
                                                     'created_on')
        response['roles'] = json_dumper(list(roles))
        response['available_roles'] = [role for role in TEAM_ROLES
                                       if role not in response['roles']]
        response['permissions'] = PROJECT_PERMISSIONS
        d = {}
        [d.update({role.role: self.generate_readable_permission_json(role)})
         for role in roles]
        response['project_permissions_map'] = d
        self.write(json.dumps(response))

