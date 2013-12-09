import ast
from datetime import datetime
import urllib

from tornado.web import HTTPError
from mongoengine import ValidationError
from mongoengine.queryset import Q
from requires.base import BaseHandler, authenticated
from datamodels.session import SessionManager
from datamodels.project import Project
from datamodels.team import Team
from datamodels.team import Invitation
from datamodels.user import User
from asyncmail import AsycnEmail
from datamodels.organization import Organization
from datamodels.project import Project
from utils.dumpers import json_dumper


class UserHandler(BaseHandler):

    SUPPORTED_METHODS = ('GET','PUT','POST','DELETE')
    REQUIRED_FIELDS = {
        'PUT': ('username','password','email')
        }
    
    def clean_oauth_data(self, oauth_data):
        return ast.literal_eval(urllib.unquote(oauth_data))

    def add_invited_user(self, user=None, code=None):
        '''
            This method is called if a key "invite" is in put data.
            
            This method call adds an invited user to the project(s).
        '''
        invitation = None
        try:
            invitation = Invitation.objects.get(code=code,
                                        valid_until__gte=datetime.utcnow())
        except Invitation.DoesNotExist:
            raise HTTPError(404, **{'reason': "Invalid token"})
        
        if invitation:
            invitations = Invitation.objects.filter(email=invitation.email)
            for each in invitations:
                project, role = each.project, each.role
                project.members.extend([user])
                project.update(set__members=set(project.members))
                new_user = Team(user=user,
                                 project=project,
                                 role=role,
                                 created_by=self.current_user,
                                 updated_by=self.current_user)
                new_user.save()
            invitations.delete()

    def put(self, *args, **kwargs):
        """
        Register a new user
        """
        data = self.data
        code = None
        _oauth = _provider = None
        if 'google_oauth' in data.keys():
            _oauth, _provider = self.clean_oauth_data(data['google_oauth']) , 'google'
            data.pop('google_oauth')
        if 'github_oauth' in data.keys():
            _oauth, _provider = self.clean_oauth_data(data['github_oauth']) , 'github'
            data.pop('github_oauth')
        
        if 'invite' in data.keys():
            code = data['invite']
            data.pop('invite')
            
        user = User(**data)
        # Password has to be hashed
        user.password = SessionManager.encryptPassword(user.password)
        try:
            user.save(validate=True, clean=True)
            user.update_profile(_oauth=_oauth, _provider=_provider)
#            async_email = AsycnEmail(self.request)
#            async_email.generate_publish_content(user=user)
#            async_email.send_email(email=user.email)
            if code: self.add_invited_user(user=user, code=code)
        except ValidationError, error:
            raise HTTPError(403, **{'reason': self.error_message(error)})
        
        if user:
            self.finish({
                'status': 200,
                'message': 'User registered successfully'
            })

    @authenticated
    def get(self, username, *args, **kwargs):
        if not username:
            username = self.current_user.username
        try:
            response = {}
            user = User.objects.get(username=username)
            response['organization'] = [org.name for org in user.belongs_to]
            response['user'] = user.to_json()
            self.write(response)
        except User.DoesNotExist:
            self.send_error(404)

    def post(self, *args, **kwargs):
        pass

    def delete(self, *args, **kwargs):
        pass


