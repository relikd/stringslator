#!/usr/bin/env python3

import os
import sys
import sqlite3  # v3.3+
import plistlib
import codecs
import re
import argparse

scriptFilePath = os.path.realpath(__file__)
scriptRoot = os.path.abspath(os.path.join(scriptFilePath, os.pardir))
PATH_DB = os.path.join(scriptRoot, 'stringslator.db')


def main():
    ARGSParser().parse()

# --------------------------------------------
#
#                 StringsDB
#
# --------------------------------------------


class StringsDB(object):
    """ Communication with, and processing of stringslator db """
    db = None
    sql = None

    def __init__(self):
        super(StringsDB, self).__init__()
        self.db = sqlite3.connect(PATH_DB)
        self.sql = self.db.cursor()
        self.createTablesIfNeeded()

    def __del__(self):
        self.db.commit()
        self.db.close()

    # --------------------------------------------
    #               stringslator API
    # --------------------------------------------

    def apiInfo(self, f_id, isComponent=False):
        """ Return 3-tuple (dbFetchFile(), dbFetchComponents(), dbFetchCounts())
        """
        if isComponent:
            f_id = self.fetchFileFromComponent(f_id)
        file = self.fetchFile(f_id)
        if file is None:
            return None, None, None
        return file, self.fetchComponents(f_id), self.fetchCounts(f_id)

    def apiSearch(self, term, titlesearch=False, langs=["en%"]):
        """ Argument takes search term (use '%' for ambiguous matching).
        If titlesearch = True, match all rows where title matches exactly.
        Return array of tuples (f_id, c_id, l_id, title, translation)
        """
        if titlesearch:
            self.sql.execute("SELECT * FROM _trans WHERE key LIKE ?", [term])
        else:
            langIds = self.fetchLanguageIDs(langs)
            lParam = ','.join('?' * len(langIds))
            self.sql.execute('''SELECT * FROM _trans WHERE value LIKE ?
                                AND lid IN (%s)''' % lParam, [term] + langIds)
        return self.sql.fetchall()

    def apiExport(self, c_id, key):
        """ Return array of tuples (lang, translation) """
        self.sql.execute('''
            SELECT l.name, t.value
            FROM _trans t INNER JOIN _lang l ON l.id = t.lid
            WHERE cid = ? and key = ?
            ORDER BY l.name COLLATE NOCASE''', [c_id, key])
        return self.sql.fetchall()

    def apiAdd(self, path, recursive=False):
        """ Add path to db by enumerating all string files (recursively) """
        for resPath in enumerateResourcePaths(path, recursive):
            self.insertResourceIntoDB(resPath)

    def apiDelete(self, idOrPath, recursive=False):
        """ Delete an application with given file-id or path.
        Recursive = True is used for paths only.
        """
        if idOrPath.isdigit():
            file = self.fetchFile(idOrPath)
            if not file:
                print("id %s does not exist." % idOrPath)
            else:
                yield self.deleteFile(idOrPath), file[1]
        else:
            for f_id, name in self.fetchFileIdsWithPath(idOrPath, recursive):
                yield self.deleteFile(f_id), name

    def apiList(self, table, term=None):
        """ table is either 'file', 'comp', 'lang', or 'title'
        term is either row-id or name like %string%
        """
        TB = {"file": "_file", "comp": "_comp", "lang": "_lang"}
        if table not in TB:
            return None
        tbl = TB[table]
        stmt = ""
        if term:
            if term.isdigit():
                stmt = "WHERE id = %d" % int(term)
            else:
                stmt = "WHERE name like '%%%s%%'" % term

        self.sql.execute('''SELECT id,name FROM %s %s
                            ORDER BY name COLLATE NOCASE''' % (tbl, stmt))
        return self.sql.fetchall()

    def apiListTitles(self, f_id):
        """ Return a list of all keys for a given component-id """
        self.sql.execute('''SELECT cid,key FROM _trans WHERE fid=? GROUP BY key
                            ORDER BY key COLLATE NOCASE''', [f_id])
        return self.sql.fetchall()

    # --------------------------------------------
    #           SQLite management helper
    # --------------------------------------------

    def createTablesIfNeeded(self):
        """ Set schema if not already present """
        self.sql.execute('''CREATE TABLE IF NOT EXISTS _file (
            id integer NOT NULL PRIMARY KEY,
            name text,
            dir text
        )''')
        self.sql.execute('''CREATE TABLE IF NOT EXISTS _comp (
            id integer NOT NULL PRIMARY KEY,
            fid integer NOT NULL REFERENCES _file(id),
            name text
        )''')
        self.sql.execute('''CREATE TABLE IF NOT EXISTS _lang (
            id integer NOT NULL PRIMARY KEY,
            name text
        )''')
        self.sql.execute('''CREATE TABLE IF NOT EXISTS _trans (
            fid integer NOT NULL REFERENCES _file(id),
            cid integer NOT NULL REFERENCES _comp(id),
            lid integer NOT NULL REFERENCES _lang(id),
            key text,
            value text
        )''')

    def fetchIdForTable(self, table, cols=[], vals=[]):
        """ Fetch row-id for given table, columns, and values """
        if len(cols) != len(vals):
            raise Exception("COLS and VALS are not of same length")
        cols = [x + "=?" for x in cols]
        self.sql.execute('SELECT id FROM %s WHERE %s' %
                         (table, " AND ".join(cols)), vals)
        return self.sql.fetchone()

    def insertIdIntoTable(self, table, cols=[], vals=[]):
        """ Insert new row into table with given values """
        if len(cols) != len(vals):
            raise Exception("COLS and VALS are not of same length")
        self.sql.execute('INSERT INTO %s(%s) VALUES (%s)' % (
            table, ','.join(cols), ','.join('?' * len(vals))), vals)
        return self.sql.lastrowid

    def insertOrReturnRowID(self, table, cols, vals=[]):
        """ Return tuple (row-id, didExistBeforeFlag) """
        idn = self.fetchIdForTable(table, cols.split(','), vals)
        if idn is None:
            return self.insertIdIntoTable(table, cols.split(','), vals), False
        else:
            return idn[0], True

    def insertFile(self, path, name):
        """ Return row id of _file table. Insert new one if necessary. """
        return self.insertOrReturnRowID('_file', 'name,dir', [name, path])

    def insertComponent(self, f_id, comp):
        """ Return row id of _comp table. Insert new one if necessary. """
        return self.insertOrReturnRowID('_comp', 'fid,name', [f_id, comp])[0]

    def insertLang(self, lang):
        """ Return row id of _lang table. Insert new one if necessary. """
        return self.insertOrReturnRowID('_lang', 'name', [lang])[0]

    def fetchLanguageIDs(self, langs=[]):
        """ Return list of ids matching provided langs array """
        if not langs or type(langs) is not list or len(langs) == 0:
            raise Exception("fetchLanguageIDs arg is not a list or empty")
        self.sql.execute("SELECT id FROM _lang WHERE %s" %
                         " OR ".join(["name LIKE ?"] * len(langs)), langs)
        return [x[0] for x in self.sql]

    def fetchFileFromComponent(self, c_id):
        """ Return file-id with given component-id """
        self.sql.execute('SELECT fid FROM _comp WHERE id=?', [c_id])
        return self.sql.fetchone()[0]

    def fetchFile(self, f_id):
        """ Return tuple (file-id, file-name, file-dir) """
        self.sql.execute('SELECT id,name,dir FROM _file WHERE id=?', [f_id])
        return self.sql.fetchone()

    def fetchComponents(self, f_id):
        """ Return array of tuple (compunent-id, component-name) """
        self.sql.execute('''SELECT id,name FROM _comp WHERE fid=?
                            ORDER BY name''', [f_id])
        return self.sql.fetchall()

    def fetchCounts(self, f_id):
        """ Return tuple [languages, translations, total] """
        self.sql.execute('''SELECT count(*) FROM _trans WHERE fid=?
                            GROUP BY lid''', [f_id])
        counts = [0, 0, 0]
        for x in self.sql:
            counts[0] += 1
            counts[1] = max(x[0], counts[1])
            counts[2] += x[0]
        return counts

    def fetchFileIdsWithPath(self, path, recursive=False):
        """ Return (file-id, file-name) for matching rows.
        If recursive = True also match all subdirectories.
        """
        path = os.path.abspath(path)
        if recursive:
            path = "%s%%" % path
        self.sql.execute('SELECT id, name FROM _file WHERE dir LIKE ?', [path])
        return self.sql.fetchall()

    def deleteFile(self, f_id):
        """ Delete rows in _file, _comp, and _trans where f_id matches """
        self.sql.execute('DELETE FROM _file WHERE id=?', [f_id])
        self.sql.execute('DELETE FROM _comp WHERE fid=?', [f_id])
        self.sql.execute('DELETE FROM _trans WHERE fid=?', [f_id])
        return self.sql.rowcount  # only translations are relevant

    # --------------------------------------------
    #           Insert new application
    # --------------------------------------------

    def insertResourceIntoDB(self, path):
        """ Parse 'Resources' folder and insert all localizable strings to db.
        If path was processed before it will be skipped immediatelly.
        """
        sfe = StringsFileEnumerator(self, path)
        if not sfe.validPath:
            print("ERROR: '%s' has no 'Resources' folder." % path)
            return False
        if sfe.existing:
            print("skip existing. '%s'" % sfe.appName)
            return False

        print("processing '%s'" % sfe.appName)
        langs, trns = sfe.processResourcesFolder()

        if len(trns) > 0 and len(langs) > 1:
            self.sql.executemany('INSERT INTO _trans VALUES (?,?,?,?,?)', trns)
            self.db.commit()
            print("added id %d '%s' (%d strings, %d languages)" %
                  (sfe.fid, sfe.appName, len(trns), len(langs)))
            return True
        else:
            print("ignored, empty.")
            self.db.rollback()
            return False


# --------------------------------------------
#
#           StringsFileEnumerator
#
# --------------------------------------------


class StringsFileEnumerator(object):
    """ Helper to find all .strings files in directory 'resPath'.
    Will return array of extracted languages and translations
    """
    db = None
    resPath = None
    appName = None
    fid = 0
    existing = True
    validPath = False

    def __init__(self, stringsDB, path):
        super(StringsFileEnumerator, self).__init__()
        self.db = stringsDB
        self.resPath = self.resourcesPathForPath(path)
        if self.resPath is not None:
            self.validPath = True
            appPath = self.appDirForResourcePath(self.resPath)
            self.appName = os.path.basename(appPath)
            self.fid, self.existing = self.db.insertFile(appPath, self.appName)

    # --------------------------------------------
    #          Process .strings files
    # --------------------------------------------

    def processResourcesFolder(self):
        """ Enumerate .strings files for all languages (.lproj subfolders) """
        translations = list()
        languages = set()
        for f1, localePath in self.enumerateWithExt(self.resPath, "lproj"):
            l_id = self.db.insertLang(f1)
            for f2, locFile in self.enumerateWithExt(localePath, "strings"):
                languages.add(l_id)
                c_id = self.db.insertComponent(self.fid, f2)
                for key, val in self.processStringsFile(locFile):
                    translations.append([self.fid, c_id, l_id, key, val])
        return languages, translations

    def processStringsFile(self, stringsFile):
        """ Parse strings file (try XML, then C-source) """
        with open(stringsFile, 'rb') as fp:
            try:  # try XML format first
                plist = plistlib.load(fp)
                for key, val in self.parseStringsFileXML(plist):
                    yield key, val
                return
            except plistlib.InvalidFileException:
                pass
        try:  # then try c-style formatting
            for key, val in self.parseStringsFileCSource(stringsFile):
                yield key, val
            return
        except Exception as e:
            print("ERROR: Couldn't read plist '%s'" % stringsFile)
            raise e

    def parseStringsFileXML(self, xml, prefix=''):
        """ Parse XML style strings file with nested dicts """
        for key in xml:
            val = xml[key]
            if len(prefix) > 0:
                key = "%s.%s" % (prefix, key)
            if type(val) is dict:
                for key2, val2 in self.parseStringsFileXML(val, prefix=key):
                    yield key2, val2
            else:
                yield key, val

    def parseStringsFileCSource(self, filePath):
        """ Parse C-source-code style strings file.
        Regex will find assignments and ignore (block-)comments.
        """
        prog = re.compile(r'(?:(?!\s*/\*)(.*?)=(.*?);)|(/\*)|(\*/)')
        enc = self.findFileEncoding(filePath)
        with open(filePath, 'r', encoding=enc) as fp:
            content = fp.read()

        blockComment = False
        quotes = ["''", '""']
        for key, val, cmntA, cmntB in prog.findall(content):
            if cmntA:
                blockComment = True
            elif cmntB:
                blockComment = False
            elif not blockComment:
                key = key.strip()
                if key.startswith("//"):  # single line comment
                    continue
                val = val.strip()
                if key[0] + key[-1] in quotes:
                    key = key[1:-1]
                if val[0] + val[-1] in quotes:
                    val = val[1:-1]
                yield key, val

    def findFileEncoding(self, path):
        """ Auto detect UTF-8/-16/-32 encoding with BOM """
        with open(path, 'rb') as fp:
            header = fp.read(4)
        for bom, encoding in (
            (codecs.BOM_UTF32_BE, "utf-32-be"),
            (codecs.BOM_UTF32_LE, "utf-32-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be"),
            (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF8, "utf-8")
        ):
            if header.startswith(bom):
                break
        return encoding

    # --------------------------------------------
    #       Folder properties & enumeration
    # --------------------------------------------

    def resourcesPathForPath(self, path):
        """ Always navigate into '../Contents/Resources/' folder """
        try:
            actual = os.path.basename(os.path.normpath(path))
        except Exception:
            return None
        if actual == "Resources":
            newPath = path
        elif actual == "Contents":
            newPath = os.path.join(path, "Resources")
        else:
            newPath = os.path.join(path, "Contents", "Resources")

        if os.path.exists(newPath):
            return newPath
        return None

    def appDirForResourcePath(self, resPath):
        """ Navigate to '../../' from Resources folder """
        parent = os.path.normpath(resPath)
        while os.path.basename(parent) in ["Contents", "Resources"]:
            parent = os.path.abspath(os.path.join(parent, os.pardir))
        return parent

    def enumerateWithExt(self, resPath, extension):
        """ Enumerate all files and folders in resPath with given extension """
        for x in os.listdir(resPath):
            f, e = os.path.splitext(x)
            if e.endswith(extension):
                yield f, os.path.join(resPath, x)


# --------------------------------------------
#
#                  UserIO
#
# --------------------------------------------


class UserIO(object):
    """ Helper class for user CLI input / output """

    def __init__(self):
        super(UserIO, self).__init__()

    # https://stackoverflow.com/a/3041990
    def ask(self, question, default="yes"):
        """Ask a yes/no question via raw_input() and return their answer.

        "question" is a string that is presented to the user.
        "default" is the presumed answer if the user just hits <Enter>.
            It must be "yes" (the default), "no" or None (meaning
            an answer is required of the user).

        The "answer" return value is True for "yes" or False for "no".
        """
        valid = {"yes": True, "y": True, "ye": True,
                 "no": False, "n": False}
        if default is None:
            prompt = " [y/n] "
        elif default == "yes":
            prompt = " [Y/n] "
        elif default == "no":
            prompt = " [y/N] "
        else:
            raise ValueError("invalid default answer: '%s'" % default)

        while True:
            sys.stdout.write(question + prompt)
            choice = input().lower()
            if default is not None and choice == '':
                return valid[default]
            elif choice in valid:
                return valid[choice]
            else:
                sys.stdout.write("Please respond with 'yes' or 'no' "
                                 "(or 'y' or 'n').\n")

    def printResults(self, arr, verbose=True):
        """ Print formatted results dict or 'Nothing found' message.
        If result array contains more than 100 entries, ask user beforehand.
        """
        if arr is None or len(arr) == 0:
            print("  Nothing found.")
            return
        # s = len(arr)
        # if s > 100 and not ask("Found %d entries. Show complete list?" % s):
        #     return
        if verbose:
            print()
        if len(arr[0]) == 2:
            for i, n in arr:
                print("%5d | %s" % (i, n))
        elif len(arr[0]) == 5:
            for f, c, l, key, value in arr:
                value = value.replace('\n', '\\n')
                print("%5d | %s  ---  ('%s')" % (c, value, key))
        if verbose:
            print("\n%d results.\n" % len(arr))

    def printInfoForFile(self, file, components, counts):
        print('Info for file:')
        print('  id: %d' % file[0])
        print("  name: '%s'" % file[1])
        print("  path: '%s'" % file[2])
        print('components:')
        self.printResults(components, verbose=False)
        print("localizable strings:")
        print("   languages: %d" % counts[0])
        print("   translations: %d" % counts[1])
        print("   total: %d" % counts[2])

    def printDeletingFiles(self, delFiles):
        print("Deleting:")
        for x in sorted(delFiles):
            print("  - %s" % x)
        print()


def enumerateResourcePaths(anyPath, recursive=False):
    """ Find all subdirectories that contain '../Contents/Resources/'.
    If recursive = False just yield anyPath.
    """
    if recursive:
        # if os.path.isdir(anyPath):
        for x in os.walk(anyPath):
            # make sure ../Contents/Resources/.. exists
            if os.path.basename(x[0]) != "Contents":
                continue
            if "Resources" in x[1]:
                yield x[0]
    else:
        yield anyPath


# --------------------------------------------
#
#                 ARGSParser
#
# --------------------------------------------


class ARGSParser(object):
    """ Handle CLI parameter parsing and command calls """
    parser = None

    def __init__(self):
        super(ARGSParser, self).__init__()
        self.parser = self.initCLIParser(
            [self.cli_add, self.cli_delete, self.cli_list,
             self.cli_search, self.cli_export, self.cli_info])
        self.parser.epilog = '''
examples:
  {0} add -r '/System/' '/Applications/baRSS.app'
  {0} search '% Update%'
  {0} export 714 kWDLocPerfSignalGraphToolTip

run <command> -h to show help for command arguments'''.format(__file__)

    # ------------------------------------------------------
    #                     CLI interface
    # ------------------------------------------------------

    def cli_add(self, args):
        """ Add new application to db """
        if not args:
            return 'add', ['a'], 'Add new application to db', {
                '--recursive': (bool, 'Repeat for subdirectories'),
                'path+': (str, '<path>', 'App or Resources directory'),
            }
        sdb = StringsDB()
        for path in args.path:
            sdb.apiAdd(path, args.recursive)

    def cli_delete(self, args):
        """ Delete application from db """
        if not args:
            return 'delete', ['rm'], 'Delete application from db', {
                '--recursive': (bool, 'Delete apps in subdirectories as well'),
                'path+': (str, '<file-id|path>', 'Row-id or application path'),
            }
        sdb = StringsDB()
        Del = 0
        delFiles = []
        for path in args.path:
            for changes, filename in sdb.apiDelete(path, args.recursive):
                Del += changes
                delFiles.append(filename)

        if len(delFiles) == 0 or Del == 0:
            print("Nothing to do.")
            return
        UserIO().printDeletingFiles(delFiles)
        if not UserIO().ask("Deleting %d translations. Continue?" % Del, None):
            sdb.db.rollback()

    def cli_list(self, args):
        """ List files, components, languages, keys """
        if not args:
            return 'list', ['ls'], 'List files, components, languages, keys', {
                'mutually_exclusive': True,
                '-f?': (str, '<term>', 'list files'),
                '-c?': (str, '<term>', 'list components'),
                '-l?': (str, '<term>', 'list languages'),
                '-k': (int, '<file-id>', 'list translation keys'),
            }
        sdb = StringsDB()
        if hasattr(args, 'k'):
            UserIO().printResults(sdb.apiListTitles(args.k))
        else:
            for x, tbl in {'f': 'file', 'c': 'comp', 'l': 'lang'}.items():
                if hasattr(args, x):
                    UserIO().printResults(sdb.apiList(tbl, getattr(args, x)))

    def cli_search(self, args):
        """ Search db for translation or title-key """
        if not args:
            return 'search', ['s'], 'Search db for translation or title-key', {
                '--keys': (bool, 'search title-keys instead of translations'),
                'term': (str, '<search-term>',
                         'Search pattern using %% and _ wildcards'),
            }
        sdb = StringsDB()
        UserIO().printResults(sdb.apiSearch(
            args.term, titlesearch=args.keys, langs=["en%", "de%", "Ger%"]))

    def cli_export(self, args):
        """ Export translations for title-key """
        if not args:
            return 'export', ['e'], 'Export translations for title-key', {
                'id': (int, '<comp-id>', 'Row-id of a component'),
                'key': (str, '<title-key>',
                        'Title-key within the same component'),
            }
        sdb = StringsDB()
        for lang, text in sdb.apiExport(args.id, args.key):
            print("%s|%s" % (lang, text))

    def cli_info(self, args):
        """ Display info for file-id or component-id """
        if not args:
            return 'info', ['i'], 'Display info for file-id or component-id', {
                'id': (int, '<file-id|comp-id>',
                       'Row id of file or component (-c)'),
                '--component': (bool, 'search component-id instead of file-id')
            }
        sdb = StringsDB()
        app, components, counts = sdb.apiInfo(args.id, args.component)
        if app is None:
            print("\nFile id does not exist. Try search for an id:")
            print("  %s list -f %%Finder%%\n" % os.path.basename(__file__))
        else:
            UserIO().printInfoForFile(app, components, counts)

    # ------------------------------------------------------
    #                     argparse stuff
    # ------------------------------------------------------

    def initCLIParser(self, methods):
        """ Initialize argparse with commands from method dictionary """
        parser = argparse.ArgumentParser(add_help=False)
        parser.formatter_class = argparse.RawTextHelpFormatter
        parser.set_defaults(func=lambda x: parser.print_help(sys.stderr))
        subPrs = parser.add_subparsers(title='commands', metavar=" " * 13)
        for fn in methods:
            info = fn(None)  # call function w/o params to get info dict
            self.initCLICommand(subPrs, fn, *info)
        parser.usage = "%(prog)s <command>"
        return parser

    def initCLICommand(self, parentParser, fn, name, alias, hlp, args):
        """ Add new command (e.g., add, delete, ...) to parser """
        cmd = parentParser.add_parser(name, aliases=alias, help=hlp)
        cmd.set_defaults(func=fn)
        if name == 'list':
            cmd.epilog = '<term> can be either row-id or search string.'

        for param, options in args.items():
            if param.lower() == "mutually_exclusive":
                cmd = cmd.add_mutually_exclusive_group(required=True)
                continue
            self.initCLICommandArgument(cmd, param, options)

    def initCLICommandArgument(self, commandParser, param, options):
        """ Add command argument (e.g., -k, path, ...) to given cli command """
        args = {'help': options[-1]}
        typ = options[0]
        if param[-1] in ['?', '*', '+']:
            args['nargs'] = param[-1]
            param = param[:-1]
        if typ == bool:
            args['action'] = 'store_true'
        else:
            args['type'] = typ
            args['metavar'] = options[1]
        # make short form and prepare for unpacking
        param = [param[1:3], param] if param.startswith('--') else [param]
        opt = commandParser.add_argument(*param, **args)
        if typ != bool:
            opt.default = argparse.SUPPRESS

    def parse(self):
        """ Parse the args and call whatever function was selected """
        args = self.parser.parse_args()
        args.func(args)


if __name__ == "__main__":
    main()
