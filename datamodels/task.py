'''
Created on 12-Aug-2013

@author: someshs
'''

import sys
from datetime import datetime
from fysom import Fysom, FysomError

import mongoengine as me
from mongoengine import signals
from mongoengine import ValidationError

from datamodels.user import User
from datamodels.story import Story
from datamodels.project import Project
from datamodels.update import TaskUpdate
from utils.dumpers import json_dumper

sys.dont_write_bytecode = True


TASK_TYPES = ['Design', 'Development', 'Review', 'Testing', 'Documentation']
TITLE_REGEX = '^[a-zA-Z0-9-_\.,]*$'
DESCRIPTION_REGEX = '^[a-zA-Z0-9-_,;.\?\/\s]*$'
states = {
    'default': {
        'initial': 'New',
        'events': [
            { 'name': 'assign', 'src': ['New','Reopened','Assigned','InProgress'], 'dst': 'Assigned' },
            #{ 'name': 'reassign', 'src': ['Assigned','InProgress'], 'dst': 'Assigned' },
            { 'name': 'start', 'src': ['New','Assigned','Reopened'], 'dst': 'InProgress' },
            { 'name': 'close', 'src': ['New','Assigned','InProgress','Reopened'], 'dst': 'Closed' },
            { 'name': 'reopen', 'src': 'Closed', 'dst': 'Reopened' },
        ]
    },
    'review': {
        'initial': 'New',
        'events': [
            { 'name': 'assign', 'src': ['New', 'Reopened','Assigned','InProgress'], 'dst': 'Assigned' },
            { 'name': 'start', 'src': ['New', 'Assigned', 'Reopened'], 'dst': 'InProgress' },
            { 'name': 'submitforreview', 'src': 'InProgress', 'dst': 'ForReview' },
            { 'name': 'reviewPass', 'src': 'ForReview', 'dst': 'Reviewed' },
            { 'name': 'reviewFail', 'src': 'ForReview', 'dst': 'ReviewFail' },
            { 'name': 'fix', 'src': 'ReviewFail', 'dst': 'Fixed' },
            { 'name': 'close', 'src': ['InProgress','Reviewed','Fixed'], 'dst': 'Closed' },
            { 'name': 'reopen', 'src': 'Closed', 'dst': 'Reopened' },
        ]
    }
}


class Task(me.Document):
    """
    Task model is also a finite state machine, which is used to 
    determine the state flow for a customizable workflow
    Since multiple inheritance in python is kind of a gray area, we
    are avoiding it and instead instantiating a state property which
    holds the state machine, its properties and methods
    
    current_action is the state such as New,  Pending, Progress
    """
    
    task_type = me.StringField(choices=TASK_TYPES, required=True)
    sequence = me.IntField(unique_with=['project'], required=True)
    title = me.StringField(max_length=128)
    description = me.StringField(max_length=500)
    assigned_to = me.ReferenceField('User', dbref=True)
    estimated_effort = me.IntField()
    logged_effort = me.IntField()
    estimated_completion_date = me.DateTimeField(required=False)
    actual_completion_date = me.DateTimeField(required=False)
    current_action = me.StringField() # assign, start
    current_state = me.StringField()# New Pending
    members = me.ListField(me.ReferenceField('User', dbref=True))
    # Either parent task or child tasks
    parent_task = me.ReferenceField('self', required=False)
    child_tasks = [me.ReferenceField('self', required=False)]
    project = me.ReferenceField('Project', required=True, dbref=True)
    story = me.ReferenceField('Story', required=True, dbref=True)
    
    created_at = me.DateTimeField(default=datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.utcnow)
    created_by = me.ReferenceField('User', required=False, dbref=True)
    updated_by = me.ReferenceField('User', required=False, dbref=True)
    is_active = me.BooleanField(default=True)
#    is_pmo = me.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super(Task, self).__init__( *args, **kwargs)

    def __str__(self):
        return self.title


    def clean(self):
        tasks = Task.objects.filter(title=self.title,
                                    project=self.project,
                                    story=self.story,
                                    is_active=True).count()
        if tasks > 0:
            raise ValidationError('Duplicate Task')

    @classmethod
    def last_task_id(cls, project=None):
        sequence = None
        tasks = Task.objects.filter(project=project)
        if tasks:
            sequence = list(Task.objects.filter(project=project
                                    ).order_by('sequence'))[-1].sequence
        return sequence

    @classmethod
    def pre_save(cls, sender, document, **kwargs):
        if document.created_by and \
            document.created_by not in document.project.members:
            raise ValidationError('You do not belong to this project')
        last_sequence = cls.last_task_id(document.project)
        if last_sequence:
            document.sequence = last_sequence + 1
        else:
            document.sequence = 1
        if document.title and len(document.title) > 128:
            raise ValidationError('Title exceeds 64 characters')
        if document.description and len(document.description) > 500:
            raise ValidationError('Description exceeds 500 characters')
        if document.estimated_effort and (document.estimated_effort.bit_length() // 8) > 7:
            raise ValidationError('Too long effort.')

    @classmethod
    def post_save(cls, sender, document, **kwargs):
        '''
            1. update sequence value
            2. update members list
        '''
        if document.sequence:
            document.update(set__sequence=document.sequence)
        if document.created_by not in document.members:
            document.members = [document.created_by]
            document.update(set__members=document.members)

    def validate(self, *args, **kwargs):
        try:
            if hasattr(self, "_state_machine"):
                delattr(self, "_state_machine")
            super(Task, self).validate()
        except Exception, e:
            if e.message.find("_dynamic_fields") != -1 or\
                e.message.find("_data") != -1:
                print '_dynamic_fields error passed'
            else:
                raise e

    @property
    def state_machine(self):
        if not hasattr(self, "_state_machine"):
            if self.task_type == 'Review':
                self._state_machine = Fysom(states['review'])
            else:
                self._state_machine = Fysom(states['default'])
            # We probably need to store sm.current (which is the current state)
            # and/or current_state index in the db so that when we initialize
            # the object, we just have to set it to the current_state
            self._state_machine.current = self.current_state
            self._state_machine.current_state = self.current_state
            self._state_machine.onchangestate = self.task_on_state_change
            self._state_machine.next = self.task_next_state
        return self._state_machine


    def task_state_transition(self, data=None, user=None):
        '''
        event is same as action
        '''
        event = data['event']
        # We first check if the action is allowed
        if not self.state_machine.can(event):
            raise ValidationError("Task action not allowed")
        # Now we know that the event is allowed
        # First change the task state
        # Go ahead and update whatever data that we receive
        qParams = {
            'set__updated_at': datetime.utcnow(),
            'set__updated_by': user
        }
        # If there is no assigned user, and the action is start, 
        # then assign it to the current user
        if event == 'start':
            qParams['set__assigned_to'] = user
        # For assign, if the src and dst states are Assigned,
        # Fysom will not trigger the event. In that case, we need
        # to manually do the operation
        elif event == 'assign' and data.get('username', None):
            qParams['set__assigned_to'] = data['username']
            self.change_assignee(qParams)

        # Trigger the state transition
        getattr(self.state_machine, event)(params=qParams)

    def change_assignee(self, qParams):
        qParams['set__current_state'] = 'Assigned'
        self.update(**qParams)
        update = "Reassigned the task to %s" % (self.assigned_to['username'])
        self.create_task_update(update)

    def task_on_state_change(self, e):
        e.params['set__current_state'] = e.dst
        self.update(**e.params)
        self.state_machine.current_state = self.current_state
        self.state_machine.current = self.current_state
        text = 'Changed task from %s to %s' %(e.src, e.dst)
        self.create_task_update(text)

    def create_task_update(self, update):
        task_update = TaskUpdate(task=self,
                                 project=self.project,
                                 created_by=self.updated_by,
                                 updated_by=self.updated_by,
                                 text=update)
        task_update.save()

    def task_next_state(self):
        action = states['default']['events'][self._state_machine.current_state]['name']
        if hasattr(self.state_machine, action):
            getattr(self.state_machine, action)()

    def next_events(self):
        '''
            return a list of event based on current state of the task.
        '''
        ev = []
        for action, value in self.state_machine._map.iteritems():
            if self.state_machine.current in value.keys():
                ev.append(action)
        #if not self.assigned_to: ev.append('Assign to yourself')
        return ev
    
    def save(self, *args, **kwargs):
        '''
            call save only in case of project PUT.
            for any modification call project.update.
        '''
        super(Task, self).save(*args, **kwargs)
        self.reload()

    def update(self, *args, **kwargs):
        super(Task, self).update(*args, **kwargs)
        self.reload()

    def to_json(self, fields=None, exclude=None):
        return json_dumper(self, fields, exclude)


signals.pre_save.connect(Task.pre_save, sender=Task)
signals.post_save.connect(Task.post_save, sender=Task)


#    def validate(self, *args, **kwargs):
#        try:
#            if hasattr(self, "_state_machine"):
#                delattr(self, "_state_machine")
#            super(Task, self).validate()
#        except Exception, e:
#            if e.message.find("_dynamic_fields") != -1 or\
#                e.message.find("_data") != -1:
#                print '_dynamic_fields error passed'
#            else:
#                raise e

#    @property
#    def state_machine(self):
#        if not hasattr(self, "_state_machine"):
#            self._state_machine = Fysom(states['default'])
#        return self._state_machine
#
#    def onchangestate(self, e):
#        print 'Changing task from ' + e.src + ' to ' + e.dst
#        # Change current action to next action
#        self.current_action += 1
#
#    def next(self):
#        getattr(self, self.actions[self.current_action])()


#
#class EntityFactory:
#    """
#    Factory to create and return entities of specified type
#    """
#
#    ALLOWED_ENTITIES = ['Task','Story']
#
#    @staticmethod
#    def create(entity_type, **kwargs):
#        # Get reference to the current module (basemodel)
#        module = sys.modules[__name__]
#        # If we are allowed to create the entity
#        if entity_type in EntityFactory.ALLOWED_ENTITIES and hasattr(module, entity_type):
#            try:
#                # Try and create a new instance of the entity
#                return getattr(module, entity_type)(**kwargs)
#            except NameError:
#                return None
#        return None
#
#    @staticmethod
#    def get(entity_type, id):
#        pass
#
#
#class WorkflowDispatcher:
#    """
#    This class handles all the action attributes of a state transition
#    It invokes the entity factory to get the required entity and then performs
#    the required action on it
#    """
#    pass

