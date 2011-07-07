#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
from os.path import exists, join, split, dirname, isabs
from datetime import datetime
from tempfile import gettempdir, NamedTemporaryFile
from hashlib import md5

from fabric.api import run, put, settings, hide
from fabric.api import sudo as fab_sudo
from jinja2 import Environment, PackageLoader, FileSystemLoader

'''
Module responsible for the base Role and its operations.
'''

class UsingRole(object):
    '''ContextManager that allows using Roles in other Roles.'''
    def __init__(self, role, prov, context):
        self.role = role
        self.prov = prov
        self.context = context

    def __enter__(self):
        role = self.role(self.prov, self.context)
        role.provision()
        return role

    def __exit__(self, exc_type, exc_value, traceback):
        role = self.role(self.prov, self.context)
        role.schedule_cleanup()


class Role(object):
    '''
Base Role class. This is the class that is inherited by all provy's roles.
This class provides many utility methods for interacting with the remote server.
Sample usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.register_template_loader('my.full.namespace')
            self.execute('ls /home/myuser', sudo=False, stdout=False)
</pre>
    '''
    def __init__(self, prov, context):
        self.prov = prov
        self.context = context

    def register_template_loader(self, package_name):
        '''
Register the <<package_name>> module as a valid source for templates in Jinja2.
Jinja2 will look inside a folder called 'templates' in the specified module.
It is paramount that this module can be imported by python. The path must be well-known or be a sub-path of the provyfile.py directory.
Sample usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.register_template_loader('my.full.namespace')
</pre>
        '''
        if package_name not in self.context['registered_loaders']:
            self.context['loader'].loaders.append(PackageLoader(package_name))
            self.context['registered_loaders'].append(package_name)

    def log(self, msg):
        '''
Logs a message to the console with the hour prepended.
Sample usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.log('Hello World')
</pre>
        '''
        print '[%s] %s' % (datetime.now().strftime('%H:%M:%S'), msg)

    def schedule_cleanup(self):
        '''
Makes sure that this role will be cleaned up properly after the server has been provisioned. Call this method in your provision method if you need your role's cleanup method to be called.
Warning: If you are using the proper ways of calling roles (provision_role, using) in your role, you do not need to call this method.
Sample usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.schedule_cleanup()
</pre>
        '''
        has_role = False
        for role in self.context['cleanup']:
            if role.__class__ == self.__class__:
                has_role = True

        if not has_role:
            self.context['cleanup'].append(self)

    def provision_role(self, role):
        '''
Provisions a role inside your role. This method is the way to call other roles if you don't need to call any methods other than provision.
provision_role keeps the context and lifecycle for the current server when calling the role and makes sure it is disposed correctly.
Sample usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.provision_role(SomeOtherRole)
</pre>
        '''
        instance = role(self.prov, self.context)
        instance.provision()
        instance.schedule_cleanup()

    def provision(self):
        '''
Base provision method. This is meant to be overriden and does not do anything.
The provision method of each Role is what provy calls on to provision servers.
Sample usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            pass
</pre>
        '''
        pass

    def cleanup(self):
        '''
Base cleanup method. This is meant to be overriden and does not do anything.
The cleanup method is the method that provy calls after all Roles have been provisioned and is meant to allow Roles to perform any cleaning of resources or finish any pending operations.
Sample usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def cleanup(self):
            pass
</pre>
        '''
        pass

    def execute(self, command, stdout=True, sudo=False):
        '''
This method is the bread and butter of provy and is a base for most other methods that interact with remote servers.
It allows you to perform any shell action in the remote server. It is an abstraction over fabric's run and sudo methods.
Parameters:
stdout - Defaults to True. If you specify this argument as False, the standard output of the command execution will not be displayed in the console.
sudo - Defaults to False. Specifies whether this command needs to be run as the super-user.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.execute('ls /', stdout=False, sudo=True)
</pre>
        '''
        func = sudo and fab_sudo or run
        if stdout:
            return func(command)

        with settings(
            hide('warnings', 'running', 'stdout', 'stderr')
        ):
            return func(command)

    def execute_python(self, command, stdout=True, sudo=False):
        '''
Just an abstraction over execute. This method executes the python code that is passed with python -c.
It has the same arguments as execute.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.python_execute('import os; print os.curdir', stdout=False, sudo=True)
</pre>
        '''
        return self.execute('''python -c "%s"''' % command, stdout=stdout, sudo=sudo)

    def get_logged_user(self):
        '''
Returns the currently logged user in the remote server.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.context['my-user'] = self.get_logged_user()
</pre>
        '''
        return self.execute_python('import os; print os.getlogin()', stdout=False)

    def local_exists(self, file_path):
        '''
Returns True if the file exists locally.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            if self.local_exists('/tmp/my-file'):
                # do something
</pre>
        '''
        return exists(file_path)

    def remote_exists(self, file_path):
        '''
Returns True if the file exists in the remote server.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            if self.remote_exists('/tmp/my-file'):
                # do something
</pre>
        '''
        return self.execute('test -f %s; echo $?' % file_path, stdout=False) == '0'

    def remote_exists_dir(self, file_path):
        '''
Returns True if the directory exists in the remote server.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            if self.remote_exists_dir('/tmp'):
                # do something
</pre>
        '''
        return self.execute('test -d %s; echo $?' % file_path, stdout=False) == '0'

    def local_temp_dir(self):
        '''
Returns the path of a temporary directory in the local machine.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.context['source_dir'] = self.local_temp_dir()
</pre>
        '''
        return gettempdir()

    def remote_temp_dir(self):
        '''
Returns the path of a temporary directory in the remote server.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.context['target_dir'] = self.remote_temp_dir()
</pre>
        '''
        return self.execute_python('from tempfile import gettempdir; print gettempdir()', stdout=False)

    def ensure_dir(self, directory, owner=None, sudo=False):
        '''
Make sure the specified directory exists in the remote server.
Parameters:
directory - Directory to be created if it does not exist.
owner - If specified, the directory will be created under this user, otherwise the currently logged user is the owner.
sudo - If specified, the directory is created under the super-user. This is particularly useful in conjunction with the owner parameter, to create folders for the owner where only the super-user can write.
Sample Usage:
<pre class="sh_python">
    class MySampleRole(Role):
        def provision(self):
            self.ensure_dir('/etc/my-path', owner='myuser', sudo=True)
</pre>
        '''
        if not self.remote_exists_dir(directory):
            self.execute('mkdir -p %s' % directory, stdout=False, sudo=sudo)

        if owner:
            self.change_dir_owner(directory, owner)

    def change_dir_owner(self, path, owner):
        self.execute('cd %s && chown -R %s .' % (path, owner), stdout=False, sudo=True)

    def change_file_owner(self, path, owner):
        self.execute('cd %s && chown -R %s %s' % (dirname(path), owner, split(path)[-1]), stdout=False, sudo=True)

    def md5_local(self, file_path):
        return md5(open(file_path).read()).hexdigest()

    def md5_remote(self, file_path):
        command = "from hashlib import md5; print md5(open('%s').read()).hexdigest()" % file_path
        return self.execute_python(command, stdout=False)

    def remove_file(self, file_path, sudo=False):
        if self.remote_exists(file_path):
            self.log('File %s found at %s. Removing it...' % (file_path, self.context['host']))
            command = 'rm -f %s' % file_path
            self.execute(command, stdout=False, sudo=sudo)
            self.log('%s removed!' % file_path)
            return True
        return False

    def replace_file(self, from_file, to_file):
        put(from_file, to_file)

    def remote_symlink(self, from_file, to_file, sudo=False):
        if not self.remote_exists(from_file):
            raise RuntimeError("The file to create a symlink from (%s) was not found!" % from_file)

        command = 'ln -sf %s %s' % (from_file, to_file)
        if self.remote_exists(to_file):
            result = self.execute('ls -la %s' % to_file, stdout=False, sudo=sudo)
            if '->' in result:
                path = result.split('->')[-1].strip()
                if path != from_file:
                    self.log('Symlink has different path(%s). Syncing...' % path)
                    self.execute(command, stdout=False, sudo=sudo)
                    return True
        else:
            self.log('Symlink not found at %s! Creating...' % from_file)
            self.execute(command, stdout=False, sudo=sudo)
            return True

        return False

    def extend_context(self, options):
        extended = {}
        for key, value in self.context.iteritems():
            extended[key] = value
        for key,value in options.iteritems():
            extended[key] = value
        return extended

    def put_file(self, from_file, to_file, sudo=False):
        if sudo:
            temp_path = join(self.remote_temp_dir(), split(from_file)[-1])
            put(from_file, temp_path)
            self.execute('cp %s %s' % (temp_path, to_file), stdout=False, sudo=True)
            return

        put(from_file, to_file)

    def update_file(self, from_file, to_file, owner=None, options={}, sudo=False):
        local_temp_path = None
        try:
            template = self.render(from_file, options)

            local_temp_path = self.write_to_temp_file(template)

            if not self.remote_exists(to_file):
                self.put_file(local_temp_path, to_file, sudo)

                if owner:
                    self.change_file_owner(to_file, owner)

                return True

            from_md5 = self.md5_local(local_temp_path)
            to_md5 = self.md5_remote(to_file)
            if from_md5.strip() != to_md5.strip():
                self.log('Hashes differ %s => %s! Copying %s to server %s!' % (from_md5, to_md5, from_file, self.context['host']))
                self.put_file(local_temp_path, to_file, sudo)

                if owner:
                    self.change_file_owner(to_file, owner)

                return True
        finally:
            if local_temp_path and exists(local_temp_path):
                os.remove(local_temp_path)

        return False

    def write_to_temp_file(self, text):
        local_temp_path = ''
        with NamedTemporaryFile(delete=False) as f:
            f.write(text)
            local_temp_path = f.name

        return local_temp_path

    def read_remote_file(self, file_path, sudo=False):
        return self.execute('cat %s' % file_path, stdout=False, sudo=sudo)

    def render(self, template_file, options={}):
        if isabs(template_file):
            env = Environment(loader=FileSystemLoader(dirname(template_file)))
            template_path = split(template_file)[-1]
        else:
            env = Environment(loader=self.context['loader'])
            template_path = template_file
        template = env.get_template(template_path)

        return template.render(**self.extend_context(options))

    def is_process_running(self, process, sudo=False):
        result = self.execute('ps aux | egrep %s | egrep -v egrep;echo $?' % process, stdout=False, sudo=sudo)
        results = result.split('\n')
        if not results:
            return False
        return results[-1] == '0'

    def using(self, role):
        return UsingRole(role, self.prov, self.context)