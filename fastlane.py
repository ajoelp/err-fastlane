import os
import io
import errno
import subprocess
from errbot import BotPlugin, botcmd, arg_botcmd, webhook

class Fastlane(BotPlugin):
   

    def activate(self):
        """
        Activate the plugin
        """
        if not self.config:
            # Don't allow activation until we are configured
            message = 'Fastlane is not configured, please do so.'
            self.log.info(message)
            self.warn_admins(message)
            return
        
        self.setup_repos()
        self.setup_environments()
        super(Fastlane, self).activate()

    def setup_environments(self):
        # Update the environment variables to the ones specified in the config
        environments = os.environ.copy()
        environments['S3_KEY'] = self.config['S3_KEY']
        environments['S3_SECRET'] = self.config['S3_SECRET']
        environments['S3_BUCKET'] = self.config['S3_BUCKET']
        environments['S3_REGION'] = self.config['S3_REGION']
        os.environ.update(environments)

    def setup_repos(self):
        """Clone the projects in the configuration into the `REPOS_ROOT` if they do not exist already."""
        try:
            os.makedirs(self.config['REPOS_ROOT'])
        except OSError as exc:
            # If the error is that the directory already exists, we don't care about it
            if exc.errno != errno.EEXIST:
                raise exc

        for project_name in self.config['projects']:
            if not os.path.exists(os.path.join(self.config['REPOS_ROOT'], project_name)):
                # Possible race condition if folder somehow gets created between check and creation
                self.run_subprocess(
                    ['git', 'clone', self.config['projects'][project_name], project_name],
                    cwd=self.config['REPOS_ROOT'],
                )

    def get_configuration_template(self):
        """
        Defines the configuration structure this plugin supports

        You should delete it if your plugin doesn't use any configuration like this
        """
        return {
                'REPOS_ROOT': None,
                'S3_KEY': None,
                'S3_SECRET': None,
                'S3_BUCKET': None,
                'S3_REGION': None,
                'projects': None
               }

    def check_configuration(self, configuration):
        super(Fastlane, self).check_configuration(configuration)

    @arg_botcmd('--project-name', dest='project_name', type=str.lower, required=True)
    @arg_botcmd('--branch-name', dest='branch_name', type=str, required=True)
    def fastlane_env(self,
            message,
            project_name: str,
            branch_name: str,
    ) -> str:
        """
        run the fastlane command
        """
        self._bot.add_reaction(message, "hourglass")
        try:
            project_root = self.get_project_root(project_name)
            self.fetch_branch_from_origin(project_root, branch_name)
            fastlane_parent_directory = self.find_fastlane_directory(project_root)
            self.install_bundle(fastlane_parent_directory)
            completed_process = self.check_fastlane_env(fastlane_parent_directory)
            self._bot.remove_reaction(message, "hourglass")
            self._bot.add_reaction(message, "white_check_mark")
            return self.send_stream_request(
                    message.frm,
                    io.BytesIO(str.encode(completed_process.stdout)),
                    name='response-env.txt',
                )
        except subprocess.CalledProcessError as e:
            self._bot.remove_reaction(message, "hourglass")
            self._bot.add_reaction(message, "x")
            self.log.exception(e.output)
            self.send_stream_request(
                    message.frm,
                    io.BytesIO(str.encode(e.output)),
                    name='error-env.txt',
                )

    @arg_botcmd('--project-name', dest='project_name', type=str.lower, required=True)
    @arg_botcmd('--branch-name', dest='branch_name', type=str, required=True)
    @arg_botcmd('--environment', dest='environment', type=str, required=True)
    def fastlane(self,
            message,
            project_name: str,
            environment: str,
            branch_name: str,
    ) -> str:
        """
        run the fastlane command
        """
        os.environ['ENV'] = environment
        self._bot.add_reaction(message, "hourglass")
        try:
            project_root = self.get_project_root(project_name)
            self.fetch_branch_from_origin(project_root, branch_name)
            fastlane_parent_directory = self.find_fastlane_directory(project_root)
            self.install_bundle(fastlane_parent_directory)
            completed_process = self.build_fastlane(fastlane_parent_directory)
            self._bot.remove_reaction(message, "hourglass")
            self._bot.add_reaction(message, "white_check_mark")
            return self.send_stream_request(
                    message.frm,
                    io.BytesIO(str.encode(completed_process.stdout)),
                    name='response-%s.txt' % environment,
                )
        except subprocess.CalledProcessError as e:
            self._bot.remove_reaction(message, "hourglass")
            self._bot.add_reaction(message, "x")
            self.log.exception(e.output)
            self.send_stream_request(
                    message.frm,
                    io.BytesIO(str.encode(e.output)),
                    name='error-%s.txt' % environment,
                )
        
    
    def get_project_root(self, project_name: str) -> str:
        """Get the root of the project's Git repo locally."""
        return self.config['REPOS_ROOT'] + project_name

    @staticmethod
    def install_bundle(project_root):
        """Fetch develop from git origin."""
        return Fastlane.run_subprocess(
                ['bundle', 'install'],
                cwd=project_root,
            )

    @staticmethod
    def build_fastlane(project_root):
        """Fetch develop from git origin."""
        return Fastlane.run_subprocess(
                ['fastlane', 'deploy'],
                cwd=project_root,
            )
            
    @staticmethod
    def check_fastlane_env(project_root):
        """Fetch develop from git origin."""
        return Fastlane.run_subprocess(
                ['fastlane', 'env'],
                cwd=project_root,
            )

    @staticmethod
    def find_fastlane_directory(project_root):
        fastlane_directory = Fastlane.run_subprocess(
            ["find", project_root, "-maxdepth", "2", "-name", "fastlane", "-type", "d",  "-print", "-quit"],
            cwd=project_root).stdout
        return os.path.abspath(os.path.join(fastlane_directory, os.pardir))

    @staticmethod
    def fetch_branch_from_origin(project_root, branch_name):
        """Fetch develop from git origin."""
        for argv in [
                ['fetch', '-p'],
                ['checkout', '-B', branch_name, 'origin/{}'.format(branch_name), '-f'],
        ]:
            Fastlane.run_subprocess(
                ['git'] + argv,
                cwd=project_root,
            )

    @staticmethod
    def run_subprocess(args: list, cwd: str=None):
        """Run the local command described by `args` with some defaults applied."""
        return subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine out/err into stdout; stderr will be None
                universal_newlines=True,
                check=True,
                cwd=cwd
            )
        
