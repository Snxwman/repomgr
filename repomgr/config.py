import logging
import os
import sys
from typing import Any

import tomlkit
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.items import Table

from repomgr.cli import RepomgrCli


class Config:
    home = os.environ["HOME"]
    xdg_config_home = os.environ["XDG_CONFIG_HOME"]
    default_paths = [
        f'{xdg_config_home}/repo/repo.conf',
        f'{xdg_config_home}/repo.conf',
        f'{home}/.config/repo.conf',
        f'{home}/repo.conf',
        'config.toml'
    ]

    required_tables = ['base', 'repos']
    base_table_defaults = {
        'base_path': '~/src',
        'repo_path_format': '{host}/{owner}/{repo}',
        'update_interval': '1h',
        'git_bin': '/usr/bin/git',
        'background_fetch': True,
        'background_pull': False,
        'stash_to_pull': False,
        'nerdfonts': False,
    }
    users_table_defaults = []
    group_table_defaults = {
        'group_path': '',
        'repo_path_format': '',
        'urls': [],
        'owners': [],
    }
    repo_table_defaults = {
        'repo_name': '',
        'repo_path_format': '',
        'symlink_to': '',
        'on_pull': '',
    }


    class BaseConfig:
        def __init__(self, raw_base_table):
            Config._warn_ignoring_unknown_keys(
                'base', 
                Config.base_table_defaults.keys(), 
                list(raw_base_table.items())
            )

            Config._set_table_defaults(Config.base_table_defaults, raw_base_table)

            path_literal = raw_base_table['base_path']
            path = os.path.expanduser(path_literal)
            path = os.path.expandvars(path)
            if not os.path.isdir(path):
                msg = (
                    'Key base.base_path is not a valid directory:\n\t'
                    f'from config: {path_literal}\n\texpanded: {path}\n'
                    'You must create the base_path directory manually.'
                )
                logging.critical(msg)
                sys.exit()

            self.base_path = path
            Config.group_table_defaults['group_path'] = self.base_path

            self.repo_path_format = raw_base_table['repo_path_format']
            Config.group_table_defaults['repo_path_format'] = self.repo_path_format
            Config.repo_table_defaults['repo_path_format'] = self.repo_path_format

            self.update_interval = raw_base_table['update_interval']

            git_bin = raw_base_table['git_bin']
            if not os.path.isfile(git_bin):
                logging.critical(f'Key base.git_bin is not a file or not an absolute path: {git_bin}')

            self.git_bin = git_bin
            self.background_fetch = raw_base_table['background_fetch']
            self.background_pull = raw_base_table['background_pull']
            self.stash_to_pull = raw_base_table['stash_to_pull']

            self.nerdfonts = raw_base_table['nerdfonts']

    class GroupConfig:
        def __init__(self, raw_group_table, group_key, parent_group_path):
            Config._warn_ignoring_unknown_keys(
                group_key, 
                Config.group_table_defaults.keys(), 
                list(raw_group_table.items())
            )

            Config._set_table_defaults(Config.group_table_defaults, raw_group_table)
            key_components = group_key.split('.')

            if group_key != 'repos':
                raw_group_table.setdefault('group_path', f'.{key_components[-1]}')

            group_path = raw_group_table['group_path']
            if group_path.startswith('/'):  # Provided path is absolute
                self.group_path = group_path 

                if not os.path.isdir(self.group_path):
                    msg = (
                        f'Key {group_key}.group_path is not a valid directory: {self.group_path}'
                        'You must create the group_path directory manually if it is not a subdirectory of base.base_path.'
                    )
                    logging.critical(msg)
                    sys.exit()
            else:
                self.group_path = f'{parent_group_path}/{group_path}'

                if not os.path.isdir(self.group_path):
                    os.mkdir(self.group_path)

                    if not os.path.isdir(self.group_path):
                        logging.critical(f'Failed to create directory: {self.group_path}')
                        sys.exit()

            self.repo_path_format = raw_group_table['repo_path_format']
            self.urls = raw_group_table['urls']
            self.owners = raw_group_table['owners']

    class RepoConfig:
        def __init__(self, raw_repo_table):
            Config._warn_ignoring_unknown_keys(
                '',
                Config.repo_table_defaults.keys(),
                list(raw_repo_table.items())
            )

            Config._set_table_defaults(Config.repo_table_defaults, raw_repo_table)

            self.repo_path_format = raw_repo_table['repo_path_format']
            self.symlink_to = raw_repo_table['symlink_to']
            self.on_pull = raw_repo_table['on_pull']


    def __init__(self, cli: RepomgrCli):
        self.config_path = Config._find_config_file(cli.args.config_path)
        self.raw_config = self._read_config_file()

        self.tables = Config._extract_table_keys(self.raw_config) 
        self._check_required_tables()

        self.base = self.BaseConfig(self.raw_config['base'])
        self.repos = [] 
        self.groups = {}
        self._init_repos_groups()


    def _init_repos_groups(self):
        repos_tables = [t for t in self.tables if t.startswith('repos')]

        for group_key in repos_tables:
            if group_key == 'repos':
                parent_group_path = self.base.base_path
            else:
                parent_key = [k for k in group_key.split('.')][:-1]
                parent_key = '.'.join(parent_key)
                parent_group_path = self.groups[parent_key].group_path

            group_table = self._get_table_from_dotted_key(group_key)
            self.groups[group_key] = Config.GroupConfig(group_table, group_key, parent_group_path)


    def _split_dotted_key(self, key):
        components = key.split('.')

        # Handle case where key itself has a '.' in it by checking if the parent table exists.
        if components[0] not in self.tables:
            components = [key]

        return components

    
    def _get_table_from_dotted_key(self, key):
        key_components = self._split_dotted_key(key)

        table: Any = self.raw_config  # Type hint is to get the lsp to stop complaining.
        for k in key_components:
            table = table.get(k) 

        return table


    def _check_required_tables(self):
        missing_tables = False

        for table in Config.required_tables:
            if table not in self.tables:
                missing_tables = True
                logging.critical(f'Required table {table} not found in config')

        if missing_tables:
            sys.exit()


    @staticmethod
    def _extract_table_keys(table, parent_keys=None):
        '''Returns a list of strings representing all table keys'''
        tables = []

        for key, value in list(table.items()):
            if isinstance(value, Table) or isinstance(value, OutOfOrderTableProxy):
                full_key = f'{parent_keys}.{key}' if parent_keys else key
                tables.append(full_key)

                subtables = Config._extract_table_keys(value, full_key)
                tables.extend(subtables)

        return tables


    @staticmethod
    def _parse_table_structure(table):
        '''Returns a nested list where each element represents a table'''
        tables = []

        for key, value in list(table.items()):
            if isinstance(value, Table) or isinstance(value, OutOfOrderTableProxy):
                subtables = Config._parse_table_structure(value)

                if subtables:
                    tables.append([key, subtables])
                else:
                    tables.append([key])

        return tables


    @staticmethod
    def _set_table_defaults(table_defaults, raw_table_config):
        for key, value in table_defaults.items():
            raw_table_config.setdefault(key, value)


    @staticmethod
    def _warn_ignoring_unknown_keys(table, known_keys, present_items):
        for key, value in present_items:
            if key not in known_keys and not isinstance(value, Table) and not isinstance(value, OutOfOrderTableProxy):
                logging.warn(f'Ignoring unknown key "{key}" in {table} table of config')


    @staticmethod
    def _find_config_file(cli_arg):
        if cli_arg is not None:
            if os.path.isfile(cli_arg):
                logging.info(f'Using config file specified by cli flag: {cli_arg}')
                return cli_arg
            else:
                logging.critical(f'Config file path specified by command line argument is not a file: {cli_arg}')
                sys.exit()

        for path in Config.default_paths:
            if os.path.isfile(path):
                logging.info(f'Using config file detected at: {path}')
                return path
         
        logging.critical(f'No config file found in default locations')
        sys.exit()

    
    def _read_config_file(self):
        with open(self.config_path) as file:
            return tomlkit.load(file)

