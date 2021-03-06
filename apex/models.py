import logging
from cryptacular.bcrypt import BCRYPTPasswordManager
import transaction

from pyramid.threadlocal import get_current_request, get_current_registry
from pyramid.util import DottedNameResolver

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Table
from sqlalchemy import Unicode
from sqlalchemy import Boolean
from sqlalchemy import types
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import synonym
from sqlalchemy.sql.expression import func

from velruse.store.sqlstore import SQLBase

from zope.sqlalchemy import ZopeTransactionExtension

from apex.lib.db import get_or_create
from apex.events import UserCreatedEvent, GroupCreatedEvent, UserDeletedEvent

from apex.i18n import MessageFactory as _

DBSession = scoped_session(sessionmaker(extension=ZopeTransactionExtension()))
Base = declarative_base()

user_group_table = Table('auth_user_groups', Base.metadata,
    Column('user_id', types.Integer(),
        ForeignKey('auth_users.id', onupdate='CASCADE', ondelete='CASCADE'), primary_key=True),
    Column('group_id', types.Integer(),
        ForeignKey('auth_groups.id', onupdate='CASCADE', ondelete='CASCADE'), primary_key=True)
)

class AuthGroup(Base):
    """ Table name: auth_groups

::

    id = Column(types.Integer(), primary_key=True)
    name = Column(Unicode(80), unique=True, nullable=False)
    description = Column(Unicode(255), default=u'')
    """
    __tablename__ = 'auth_groups'
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(types.Integer(), primary_key=True)
    name = Column(Unicode(80), unique=True, nullable=False)
    description = Column(Unicode(255), default=u'')

    users = relationship('AuthUser', secondary=user_group_table, \
                     backref='auth_groups')

    def __repr__(self):
        return u'%s' % self.name

    def __unicode__(self):
        return self.name


class AuthUser(Base):
    """ Table name: auth_users

::

    id = Column(types.Integer(), primary_key=True)
    login = Column(Unicode(80), default=u'', index=True)
    username = Column(Unicode(80), default=u'', index=True)
    _password = Column('password', Unicode(80), default=u'')
    email = Column(Unicode(80), default=u'', index=True)
    active = Column(types.Enum(u'Y',u'N',u'D'), default=u'Y')
    """
    __tablename__ = 'auth_users'
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(types.Integer(), primary_key=True)
    login = Column(Unicode(80), default=u'', index=True)
    username = Column(Unicode(80), default=u'', index=True)
    _password = Column('password', Unicode(80), default=u'')
    email = Column(Unicode(80), default=u'', index=True)
    active = Column(types.Enum(u'Y',u'N',u'D', name=u"active"), default=u'Y')

    groups = relationship('AuthGroup', secondary=user_group_table, \
                      backref='auth_users')

    last_events = relationship('AuthUserLog', \
                         order_by='AuthUserLog.time.desc()')
    login_log = relationship('AuthUserLog', \
                         order_by='AuthUserLog.id')
    """
    Fix this to use association_proxy
    groups = association_proxy('user_group_table', 'authgroup')
    """


    @property
    def last_logins(self):
        return [a for a in self.last_events if a.event == 'L']

    @property
    def last_login(self):
        if self.last_logins:
            return self.last_logins[0]

    def _set_password(self, password):
        self._password = BCRYPTPasswordManager().encode(password, rounds=12)

    def _get_password(self):
        return self._password

    password = synonym('_password', descriptor=property(_get_password, \
                       _set_password))


    def in_group(self, group):
        """
        Returns True or False if the user is or isn't in the group.
        """
        return group in [g.name for g in self.groups]

    @classmethod
    def get_by_id(cls, id):
        """
        Returns AuthUser object or None by id

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser.get_by_id(1)
        """
        return DBSession.query(cls).filter(cls.id==id).first()

    @classmethod
    def get_by_login(cls, login):
        """
        Returns AuthUser object or None by login

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser.get_by_login('$G$1023001')
        """
        return DBSession.query(cls).filter(cls.login==login).first()

    @classmethod
    def get_by_username(cls, username):
        """
        Returns AuthUser object or None by username

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser.get_by_username('username')
        """
        return DBSession.query(cls).filter(cls.username==username).first()

    @classmethod
    def get_by_email(cls, email):
        """
        Returns AuthUser object or None by email

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser.get_by_email('email@address.com')
        """
        return DBSession.query(cls).filter(cls.email==email).first()

    @classmethod
    def check_password(cls, **kwargs):
        if kwargs.has_key('id'):
            user = cls.get_by_id(kwargs['id'])
        if kwargs.has_key('username'):
            user = cls.get_by_username(kwargs['username'])

        if not user:
            return False
        if BCRYPTPasswordManager().check(user.password, kwargs['password']):
            return True
        else:
            return False

    def get_profile(self, request=None):
        """
        Returns AuthUser.profile object, creates record if it doesn't exist.

        .. code-block:: python

           from apex.models import AuthUser

           user = AuthUser.get_by_id(1)
           profile = user.get_profile(request)

        in **development.ini**

        .. code-block:: python

           apex.auth_profile =
        """
        if not request:
            request = get_current_request()

        auth_profile = request.registry.settings.get('apex.auth_profile')
        if auth_profile:
            resolver = DottedNameResolver(auth_profile.split('.')[0])
            profile_cls = resolver.resolve(auth_profile)
            return get_or_create(DBSession, profile_cls, user_id=self.id)


class AuthUserLog(Base):
    """
    event:
      L - Login
      R - Register
      P - Password
      F - Forgot
    """
    __tablename__ = 'auth_user_log'
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(types.Integer, primary_key=True)
    user_id = Column(types.Integer, ForeignKey(AuthUser.id, onupdate='CASCADE', ondelete='CASCADE'), index=True)
    time = Column(types.DateTime(), default=func.now())
    ip_addr = Column(Unicode(39), nullable=False)
    internal_user = Column(Boolean, nullable=False, default=False)
    external_user = Column(Boolean, nullable=False, default=False)
    event = Column(types.Enum(u'L',u'R',u'P',u'F', name=u"event"), default=u'L')


def get_default_groups(settings):
    default_groups = []
    if settings.has_key('apex.default_groups'):
        for name in settings['apex.default_groups'].split(','):
            default_groups.append((unicode(name.strip()),u''))
    else:
        default_groups = [(u'users',u'User Group'), \
                          (u'admin',u'Admin Group')]

    return default_groups

def populate(settings):
    session = DBSession()
    default_groups = get_default_groups(settings)
    for name, description in default_groups:
        group = AuthGroup(name=name, description=description)
        session.add(group)
    session.flush()
    transaction.commit()

def initialize_sql(engine, settings=None):
    if not settings:
        settings = {}
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine
    Base.metadata.create_all(engine)
    if settings.has_key('apex.velruse_config'):
        SQLBase.metadata.bind = engine
        SQLBase.metadata.create_all(engine)
    try:
        populate(settings)
    except IntegrityError:
        transaction.abort()


def delete_user(user, request=None, registry=None):
    """
    """
    if registry is None:
        registry = get_current_registry()
    if request is None:
        request = get_current_request()
        # when request is not available fake it a bit
        if request is None:
            class obj(object): pass
            class session:
                def flash(self, *args, **kwargs):pass
            obj.registry = registry
            obj.session = session() 
            request = obj() 
    settings = registry.settings 
    try:
        transaction.commit()
        registry.notify(UserDeletedEvent(request, user))
        DBSession.delete(AuthUser.get_by_id(user.id))
        transaction.commit()
    except Exception, e:
        raise Exception('Can\'t delete user: %s' % e)
    return user

def create_user(**kwargs):
    """
::

    from apex.lib.libapex import create_user
    create_user(username='test', password='my_password', active='Y', group='group')
    Returns: AuthUser object
    """
    request = get_current_request()
    registry = get_current_registry()
    if 'registry' in kwargs:
        registry = kwargs['registry']
        del kwargs['registry']
    settings = registry.settings
    # map default groups
    groups = []
    if settings.has_key('apex.default_user_group'):
        group = DBSession.query(AuthGroup).filter(
            AuthGroup.name==settings['apex.default_user_group']).one()
        if not group in groups:
            groups.append(group)
    # add user to users groups
    qgroup = DBSession.query(AuthGroup).filter(
        AuthGroup.name=='users').first()
    if qgroup:
        if not qgroup in groups:
            groups.append(qgroup)
    # extra kw group
    if 'group' in kwargs:
        try:
            group = DBSession.query(AuthGroup).filter(
                AuthGroup.name==kwargs['group']).one()
            groups.append(group)
        except NoResultFound:
            pass
        del kwargs['group']
    # extra kw groups splitted on ','
    if 'groups' in kwargs:
        try:
            sgroups = kwargs['groups'].split(',')
            qgroups= DBSession.query(AuthGroup).filter(
                AuthGroup.name.in_(sgroups)).all()
            for group in qgroups:
                if not group in groups:
                    groups.append(group)
        except NoResultFound:
            pass
        del kwargs['groups']
    # register user
    user = AuthUser()
    for key, value in kwargs.items():
        setattr(user, key, value)
    DBSession.add(user)
    try:
        transaction.commit()
        DBSession.add(user)
        # link groups
        for group in groups:
            try:
                user.groups.append(group)
                transaction.commit()
            except Exception, e:
                error = _('Cant add user :%s to group: %s (%s)') % (user, group, e)
                logging.getLogger('apex.add_user_to_group').error(error)
                request.session.flash(error, 'error')
        transaction.commit()
        DBSession.add(user)
        # when request is not available fake it a bit
        class obj(object): pass
        class session:
            def flash(self, *args, **kwargs):pass
        obj.registry = registry
        obj.session = session()
        if request is None:
            request = obj()
        registry.notify(UserCreatedEvent(request, user))
        transaction.commit()
        DBSession.add(user)
    except Exception, e:
        raise Exception('Cant create user: %s' % e)
    return user

def create_group(**kwargs):
    """
::

    from apex.lib.libapex import create_group
    create_group(groupname='test', password='my_password', active='Y', group='group')
    Returns: AuthGroup object
    """
    group = AuthGroup()
    request = get_current_request()
    registry = get_current_registry()
    for key, value in kwargs.items():
        setattr(group, key, value)
    DBSession.add(group)
    try:
        DBSession.flush()
        transaction.commit()
        registry.notify(GroupCreatedEvent(request, group))
    except Exception, e:
        DBSession.rollback()
        raise Exception('Cant create group: %s' % e)
    return group

