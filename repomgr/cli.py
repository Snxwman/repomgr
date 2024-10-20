import argparse
import pathlib

class RepomgrCli:
    version = '0.0.1'

    def __init__(self):
        parser = argparse.ArgumentParser(prog='repo')
        subparsers = parser.add_subparsers(dest='subcmd')

        parser.add_argument('-C', '--config', type=pathlib.Path, dest='config_path', help='Specify a custom config file path')
        parser.add_argument('-v', '--verbose', action='count', default=0)
        parser.add_argument('-V', '--version', action='version', version=f'%(prog)s {RepomgrCli.version}')

        add_parser = subparsers.add_parser('add', help='Add a repo to be managed')
        add_parser.add_argument('-g', '--group', help='Specify a group to add this repo to')

        parser_del = subparsers.add_parser('del', help='Delete a repo from being managed')

        self.args = parser.parse_args()

