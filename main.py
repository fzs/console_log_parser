import logging
import argparse
import json
from os.path import dirname, isabs, splitext, exists, join
from os import makedirs
import sys
from terminal2html import parse as html_parse

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

LOG = logging.getLogger()


class TodoArgs:
    def __init__(self, args):
        self.infile = args.infile
        self.outfile = args.outfile
        self.palette = args.palette
        self.title = None


def parse_file(args):
    if args.outfile:
        if not exists(dirname(args.outfile)):
            makedirs(dirname(args.outfile))

        with open(args.outfile, 'w') as destfile:
            with open(args.infile, 'rb') as logfile:
                LOG.info("Parsing file %s", args.infile)
                html_parse(logfile, destfile, palette=args.palette, title=args.title)
    else:
        with open(args.infile, 'rb') as logfile:
            LOG.info("Parsing file %s", args.infile)
            html_parse(logfile, palette=args.palette, title=args.title)


# def join(path, file):
#     """ Redefined join since even under windows we work in a Linux shell """
#     return path + '/' + file


def process_file_list(args, file_list_file):
    with open(file_list_file, 'r') as file_list:
        data = json.load(file_list)

        base_dir_in = dirname(file_list_file)
        if 'base_dir_in' in data and data['base_dir_in']:
            dir = data['base_dir_in']
            if isabs(dir):
                base_dir_in = dir
            else:
                base_dir_in = join(base_dir_in, dir)

        base_dir_out = dirname(file_list_file)
        if 'base_dir_out' in data and data['base_dir_out']:
            dir = data['base_dir_out']
            if isabs(dir):
                base_dir_out = dir
            else:
                base_dir_out = join(base_dir_out, dir)

        if data['files']:
            for file in data['files']:
                in_file = join(base_dir_in, file['in'])
                if 'out' in file and file['out']:
                    out_file = join(base_dir_out, file['out'])
                else:
                    base, ext = splitext(file['in'])
                    out_file = join(base_dir_out, base + '.html')

                my_args = TodoArgs(args)
                my_args.infile = in_file
                my_args.outfile = out_file
                if 'palette' in file and file['palette']:
                    my_args.palette = file['palette']
                if 'title' in file and file['title']:
                    my_args.title = file['title']

                print("Process")
                print(f"    {my_args.infile}")
                print(f" -> {my_args.outfile}")
                print(f" as {my_args.title}")
                print(f" in {my_args.palette}")
                sys.stdout.flush()

                parse_file(my_args)


def main():
    """
    main.py [<options>] <infile> [<outfile>]
      <infile> logfile to convert
      <outfile> HTML file to write to. Default is standard out.
    """
    argparser = argparse.ArgumentParser(description="Convert a terminal log file into processed output, e.g. HTML")
    argparser.add_argument('infile', help="terminal log input file")
    argparser.add_argument('outfile', nargs='?', help="HTML file to write to. Default is stdout")
    argparser.add_argument('--MyDracula', '--MyDarcula', '--local', dest='palette', action='store_const', const='MyDracula',
                           help="Use color palette MyDracula (default)")
    argparser.add_argument('--Dracula', '--Darcula', '--remote', dest='palette', action='store_const', const='Dracula',
                           help="Use color palette Dracula")
    argparser.add_argument('--TangoDark', dest='palette', action='store_const', const='TangoDark',
                           help="Use color palette Tango Dark")
    argparser.add_argument('--list', '-l', action='store_true', dest='filelist',
                           help="The input file is a JSON todo list with files to convert and their options")
    args = argparser.parse_args()

    if args.filelist:
        process_file_list(args, args.infile)
    else:
        args.title = ''
        parse_file(args)


if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="parser.log",
                        level=logging.INFO,
                        format=LOG_FORMAT,
                        filemode='w')
    main()
