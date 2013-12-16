'''
Created on 16-Aug-2013

@author: someshs
'''

import ast
from tornado.web import HTTPError
from tornado import template
from requires.base import BaseHandler, authenticated
from asyncmail import AsycnEmail
from datamodels.project import Project
from datamodels.user import User
from datamodels.team import Team, Invitation
from mongoengine.errors import ValidationError
from utils.dumpers import json_dumper
from datamodels.permission import Role
import json
from requires.settings import PROJECT_PERMISSIONS, SETTINGS


class TeamHandler(BaseHandler):

    SUPPORTED_METHODS = ('GET', 'POST', 'DELETE')
    REQUIRED_FIELDS = {
        'POST': ('data',),
        'DELETE' : ('usernames', 'projectId'),
        }
    data = {}

    def _get_role(self, invite_data):
        """
        Role get helper
        """
        try:
            role = Role.objects.get(
                role=invite_data['role'],
                project=self.project)
            return role
        except Role.DoesNotExist:
            raise HTTPError(404, **{
                'reason': 'Please create %s from project settings '
                          'first.' % invite_data['role']})


    def clean_request(self, project):
        '''
            function to remove additional data key send in request.
            e.g token

            Besides above, it also cleans the date-time values and duration
        '''
        self.data['members'] = []
        self.data['new_members'] = []
        for each in self.data['data']:
            try:
                user = User.objects.get(email=each['email'])
                role = self._get_role(each)
                self.data['members'].append({'user': user,
                                             'role': role})
                self.data['new_members'].append(user)
            except User.DoesNotExist:
                self.invitations.append(
                    self.create_invitation(each['email'],
                    self._get_role(each)))
                #raise HTTPError(404, **{'reason': each['email'] + ' not found '})

    def create_invitation(self, email, role):
        """
        Create invitation objects if email for
        user is not found in the system
        """
        invitation = Invitation(
            email=email,
            project=self.project,
            invited_by=self.current_user,
            role=role)
        invitation.save()
        async_email = AsycnEmail(self.request)
        template = SETTINGS['template_path']+'/'+'invite_mailtemplate.html'
        params={'project_name': invitation.project.title,
                'project_owner': invitation.project.created_by.username,
                'code':  invitation.code}
        async_email.generate_subject_content(subject='Welcome to Clearsoup.')
        async_email.send_email(
           email=invitation.email, template=template, params=params,
           from_email=SETTINGS['no-reply_email'],
           reply_to=SETTINGS['feedback_email'])
        return json_dumper(invitation)

    def get_project_object(self, project_id=None, permalink=None):
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

    def check_permission(self, project, value):
        team = None
        try:
            team = Team.objects.get(project=project,
                                       user=self.current_user)
            permission_flag = False
            if Role.testBit(team.role.map,
                                 PROJECT_PERMISSIONS.index(value)):
                permission_flag = True
            return permission_flag
        except Team.DoesNotExist:
            msg = 'Not permitted to perform this action'
            raise HTTPError(500, **{'reason':msg})

    @authenticated
    def get(self,*args, **kwargs):
        project_id = self.get_argument('projectId', None)
        project = self.get_project_object(project_id=project_id,
                                          permalink=None)
        self.project = project
        response = {}
        members = list(Team.objects.filter(project=project).exclude("project",
                                                    "created_by", "updated_by"))
        invited_members = list(Invitation.objects.filter(project=project
                                             ).exclude('invited_by', 'project'))
        response['members'] = json_dumper(members)
        response['invited_members'] = json_dumper(invited_members)
        self.write(json.dumps(response))

    @authenticated
    def post(self, *args, **kwargs):
        '''
            new data set
            [{'email': email, 'role': role}, {'email': email, 'role': role}]
        '''
        project_id = self.get_argument('projectId', None)
        project_permalink = self.get_argument('project_permalink', None)
        project = None
        self.invitations = []
        if project_id:
            project = self.get_project_object(project_id=project_id,
                                              permalink=None)
        elif project_permalink:
            project = self.get_project_object(project_id=None,
                                              permalink=project_permalink)

        if not self.check_permission(project, 'can_add_member'):
            raise HTTPError(403,
                reason="Not permitted to add members to this project")

        self.project = project
        self.clean_request(project)
        response = {}
        response['members'] = []
        for each in self.data['members']:
            new_user = existing_user = None
            project.members.extend(self.data['new_members'])
            project.update(set__members=set(project.members))
            try:
                existing_user = Team.objects.get(user=each['user'],
                                              project=project)
                existing_user.update(set__role=each['role'])
            except Team.DoesNotExist:
                new_user = Team(user=each['user'],
                                 project=project,
                                 role=each['role'],
                                 created_by=self.current_user,
                                 updated_by=self.current_user)
                new_user.save()
#            exclude = ['udpated_at', 'updated_by', 'created_at', 'created_by']
            if new_user:
                response['members'].append(new_user.to_json())
            elif existing_user:
                response['members'].append(existing_user.to_json())
        response.update({'invitations': self.invitations})
        self.write(json_dumper(response))

    def clean_delete_request(self):
        self.data['members'] = []
        self.data['new_members'] = []
        for each in self.data['data']:
            try:
                user = User.objects.get(email=each['email'])
                self.data['members'].append({'user': user})
                self.data['new_members'].append(user)
            except User.DoesNotExist:
                raise HTTPError(404, **{'reason': each['email'] + ' not found '})

    @authenticated
    def delete(self, *args, **kwargs):
        project_id = self.get_argument('projectId', None)
        project_permalink = self.get_argument('project_permalink', None)
        project = None
        if project_id:
            project = self.get_project_object(project_id=project_id,
                                              permalink=None)
        elif project_permalink:
            project = self.get_project_object(project_id=None,
                                              permalink=project_permalink)
        if not self.check_permission(project, 'can_delete_member'):
            raise HTTPError(403,
                reason="Not permitted to delete members of this project")
        self.clean_delete_request()
        existing_members = project.members
        [Team.objects.filter(user=each,project=project).delete()
         for each in self.data['members']]
        [existing_members.pop(existing_members.index(each)) for each in
         self.data['members']]
        project.update(set__members=existing_members)
        self.write(project.to_json())


