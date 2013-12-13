import sys

sys.dont_write_bytecode = True

from tornado.web import Application, os, StaticFileHandler
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado import template

# from tornadomail.message import EmailMessage, EmailMultiAlternatives
from tornadomail.backends.smtp import EmailBackend


class ClearSoupApp(Application, object):
    """ Overridden application class from tornado.web for async mail. """

    def __init__(self, *args, **kwargs):
        super(ClearSoupApp, self).__init__(*args, **kwargs)

    @property
    def mail_connection(self):
        return EmailBackend(
            'smtp.gmail.com', 587,
            'No-Reply@clearsoup.in',
            'noreply@123',
            True,
            template_loader=template.Loader('.')
            
        )

# Use this lambda to generate absolute path for template/static.
GEN_PATH = lambda path: os.path.join(os.getcwd(), path)

SETTINGS = {
    'APPS': ['invitation', 'profile','project', 'story','auth', 'core', 'user', 'team',
             'permission', 'sprint', 'update', 'task', 'search', 'websocket',
             'admin', 'feedback'
            ],
    # Security
    'cookie': 'token',  # Specify the cookie variable name
    'login_url': '/api/authenticate/',  # Login path for the application
    'cookie_secret': '$2a$12$/Afye1F0vhEK.EPm0xYLdebypPjz0tnI.iiYhpIUMmCjCnsBwNd/6',
    'template_path': GEN_PATH('templates'),
    'static_path': GEN_PATH('assets'),
    # Templating
    'debug': True,  # Retain debug True for development.
    # App options
    'mongo_port': 8800,
    'mongo_db': 'clearsoup-db',
    'api_root': 'http://localhost:9000/api/',
    'web_root': 'http://www.clearsoup.in/',
    'models_package': 'datamodels',
    'default_avatar': 'http://www.clearsoup.in/assets/images/avatar.png',
    'no-reply_email': 'No-Reply@clearsoup.in',
    'feedback_email': 'info@clearsoup.in',
}

PROJECT_PERMISSIONS = ('can_add_story', 'can_edit_story', 'can_delete_story',
                      'can_add_task', 'can_edit_task', 'can_delete_task',
                      'can_edit_project', 'can_delete_project','can_add_member',
                      'can_edit_member', 'can_delete_member',)

ORGANIZATION_PERMISSIONS = ('can_add_project', 'can_edit_project',
                            'can_delete_project','can_add_member',
                            'can_edit_member', 'can_delete_member',)

ADMIN_ROLES = ['Administrator', 'Project Manager']
TEAM_ROLES = ['Designer', 'Development Engineer', 'Lead',
              'Engineering Manager', 'Business Analyst',
              'Engineering Manager', 'Test Engineer']

#PROJECT_ROLES = ADMIN_ROLES + TEAM_ROLES
PROJECT_ROLES = ('Administrator',)  # Fixed 10/29/13

permission_map = {'Administrator': 2047, 'Project Manager': 2047,
                  'Designer': 283, 'Development Engineer': 283, 'Lead': 283,
                  'Engineering Manager': 283, 'Business Analyst': 283,
                  'Engineering Manager': 283, 'Test Engineer': 283}

SUPERUSERS = ('suk','somesh','techiev2','srinath')

URLS = []

if SETTINGS['APPS']:
    for app in SETTINGS['APPS']:
        sys.path.append(os.path.join(os.getcwd(), app))
        _urls = __import__(app)
        URLS.extend(_urls.URLS)

APP = ClearSoupApp(URLS, **SETTINGS)
SERVER = HTTPServer(APP)
LOOP = IOLoop.instance()
PORT = 9000  # Default port. main.py picks the default from here.

