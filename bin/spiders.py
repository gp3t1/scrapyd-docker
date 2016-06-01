#!/usr/bin/env python
import argparse
import git
import getpass
import json
import logging
import os
import re
import requests
import subprocess
import sys
import time
import traceback
from crontab import CronTab
from functools32 import lru_cache
from scrapyd_api import ScrapydAPI

logs_path = os.path.join(os.environ.get('SCRAPYD_INSTALL', './'), 'logs')
logging.basicConfig(filename=os.path.join(logs_path, 'spiders.log'),
                    format='%(asctime)s %(levelname)s:%(message)s',
                    datefmt='%Y/%m/%d %H:%M:%S',
                    level=logging.INFO)


class __SpidersError__(Exception):
    def __init__(self, message):
        logging.error(message)
        # Call the base class constructor with the parameters it needs
        super(__SpidersError__, self).__init__(message)


class __SpidersCtx__(object):
    """docstring for __SpidersCtx__"""

    def __init__(self):
        super(__SpidersCtx__, self).__init__()
        logging.info("[SPIDERS CONTEXT] path              : %s", self.spiders_path())
        logging.info("[SPIDERS CONTEXT] logs path         : %s", self.logs_path())
        logging.info("[SPIDERS CONTEXT] export path       : %s", self.export_path())
        logging.info("[SPIDERS CONTEXT] configuration file: %s", self.spiders_json())
        logging.info("[SPIDERS CONTEXT] scrapyd user      : %s", self.scrapyd_user())
        logging.info("[SPIDERS CONTEXT] scrapyd api       : %s", self.scrapyd_api())

    @lru_cache(maxsize=1)
    def scrapyd_api(self):
        return os.environ.get('SCRAPYD_API', 'http://localhost:6800/')

    @lru_cache(maxsize=1)
    def scrapyd_user(self):
        user = os.environ.get('SCRAPYD_USER')
        if not user:
            raise __SpidersError__("scrapyd user not found")
        if user != getpass.getuser():
            raise __SpidersError__("This script must be run as {}".format(user))
        return user

    @lru_cache(maxsize=1)
    def export_path(self):
        epath = os.environ.get('EXPORT_PATH')
        if not epath:
            raise IOError("No export path!")
        else:
            if not os.path.isdir(epath):
                raise IOError("{} is not a folder!".format(epath))
            else:
                return epath

    @lru_cache(maxsize=1)
    def logs_path(self):
        lpath = os.environ.get('SCRAPYD_LOGS')
        if not lpath:
            raise IOError("No log path!")
        else:
            if not os.path.isdir(lpath):
                raise IOError("{} is not a folder!".format(lpath))
            else:
                return lpath

    @lru_cache(maxsize=1)
    def spiders_path(self):
        spath = os.environ.get('SPIDERS_PATH')
        if spath and os.path.isdir(spath):
            return spath
        else:
            raise __SpidersError__("Invalid spider path: {}".format(spath))

    @lru_cache(maxsize=1)
    def spiders_json(self):
        sfile = os.path.join(self.spiders_path(), 'spiders.json')
        if not os.path.isfile(sfile):
            try:
                logging.warn("Generate an empty config file in %s", sfile)
                data = {'spiders': {}}
                with open(sfile, 'w+') as f:
                    json.dump(data, f)
            except:
                msg = "Cannot find nor generate a config file "
                "for spiders in {}".fomat(self.spiders_path())
                raise __SpidersError__(msg)
        return sfile

    def isScrapydUp(self):
        try:
            r = requests.get(self.scrapyd_api())
            return r.status_code == 200
        except:
            return False

    def printCronJobs(self):
        logging.info("Cron jobs :")
        usercron = CronTab(user=self.scrapyd_user())
        for job in usercron:
            enableflag = '  ' if job.is_enabled() else '##'
            validflag = 'OK' if job.is_valid() else 'KO'
            logging.info("%s%s: %s", enableflag, validflag, job)

    def addCronJob(self, command, comment, slices):
        try:
            usercron = CronTab(user=self.scrapyd_user())
            job = usercron.new(command=command)  # , comment=comment
            job.setall(slices)
            if job.is_valid():
                if not job.is_enabled():
                    job.enable()
            usercron.write(user=self.scrapyd_user())
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback,
                                      limit=2, file=sys.stdout)
            raise __SpidersError__("Cannot add {} {} {} to crontab({})".format(
                slices, command, comment, self.scrapyd_user()))

    def cleanCronTab(self):
        emptycron = CronTab()
        emptycron.write(user=self.scrapyd_user())

    def findFile(self, folder, filename):
        """Find first file with the given filename in spider folder."""
        if os.path.isdir(folder):
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if file == filename:
                        return os.path.join(root, file)
        else:
            msg = "spider folder ({}) doesn't exist".format(folder)
            raise IOError(msg)
        msg = "file {} not found in {}".format(filename, folder)
        raise IOError(msg)


class __ScrapyProject__(object):
    """
        Instanciate a scrapy project from foldername
        , fetch data from spiders.json
        , check inconsistencies
    """

    def __init__(self, ctx, foldername):
        super(__ScrapyProject__, self).__init__()
        self.ctx = ctx
        if not os.path.isdir(ctx.spiders_path()):
            raise AttributeError("spiders_path is not a valid folder")
        if not os.path.isfile(ctx.spiders_json()):
            msg = "spiders config ({}) not found".format(ctx.spiders_json())
            raise AttributeError(msg)
        if not foldername:
            raise AttributeError("foldername is empty")
        self.name = foldername
        self.path = os.path.join(ctx.spiders_path(), self.name)
        try:
            with open(ctx.spiders_json(), 'r') as f:
                data = json.load(f)['spiders'].get(self.name, None)
            self.cron = data.get('cron')
            self.giturl = data.get('giturl', None)
            self.custom_settings = data.get('custom_settings', {})
            export_path = os.path.join(ctx.export_path(), self.name)
            if not os.path.isdir(export_path):
                os.mkdir(export_path)
            self.custom_settings['EXPORT_PATH'] = export_path
            self.custom_settings['LOG_LEVEL'] = 'INFO'
            self.custom_settings['LOG_FORMAT'] = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
            self.custom_settings['LOG_DATEFORMAT'] = '%Y-%m-%d %H:%M:%S'
            self.custom_settings['LOG_FILE'] = os.path.join(
                ctx.logs_path(), "{}.log".format(self.name))
            self.custom_args = data.get('custom_args', {})
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback,
                                      limit=2, file=sys.stdout)
            msg = "error fetching config for spider {} in {}".format(self.name,
                                                                     ctx.spiders_json())
            raise AttributeError(msg)
        # if not re.search(
        #     '([0-9,-/]*|\*) ([0-9,-/]*|\*) ([0-9,-/]*|\*) ([a-zA-Z,-/]*|\*) ([a-zA-Z,-/]*|\*)',
        #     self.cron):
        #     raise AttributeError("invalid cron config {}".format(self.cron))
        if not re.search('(http[s]?://.*\.git)', self.giturl):
            raise AttributeError("invalid git repo url {}".format(self.giturl))
        self.checkFolderInconsistencies()
        self.settings = ctx.findFile(self.path, 'settings.py')
        self.cleanSettings()
        self.scrapycfg = ctx.findFile(self.path, 'scrapy.cfg')
        self.projectname = self.getProjectName(self.scrapycfg)

    def checkFolderInconsistencies(self):
        if self.giturl:
            if os.path.isdir(self.path):
                giturlFromDisk = self.gitRepofromDisk(self.path)
                if self.giturl and giturlFromDisk != self.giturl:
                    msg = "Invalid spider {}: url={}, url_found={}".format(
                        self.name, self.giturl, giturlFromDisk)
                    raise __SpidersError__(msg)
                else:
                    git.cmd.Git(self.path).pull()
            else:
                git.cmd.Git(self.ctx.spiders_path()).clone(self.giturl, self.name)
        else:
            if not os.path.isdir(self.path):
                msg = "Invalid spider {}: folder {} found".format(
                    self.name, self.path)
                raise __SpidersError__(msg)

    def cleanSettings(self):
        logging.info("clean project %s settings (log config...)", self.name)
        with open(self.settings, "r+") as f:
            lines = f.readlines()
            f.seek(0)
            for line in lines:
                filtered = False
                filters = ['LOG_LEVEL =', 'LOG_FORMAT =', 'LOG_DATEFORMAT =', 'LOG_FILE =']
                for filtr in filters:
                    if line.startswith(filtr):
                        filtered = True
                if not filtered:
                    f.write(line)
            f.truncate()
            f.close()

    def setDeployTarget(self, targetname):
        configured = False
        with open(self.scrapycfg, 'r') as f:
            for line in f.read():
                if "[deploy:{}]".format(targetname) in line:
                    configured = True
        if not configured:
            with open(self.scrapycfg, 'a') as f:
                f.write("\n[deploy:{}]".format(targetname))
                f.write("\nurl = {}".format(self.ctx.scrapyd_api()))
                f.write("\nproject = {}".format(self.projectname))
                if self.giturl:
                    f.write('\nversion = GIT')
                f.write('\n')

    def registerSpiders(self):
        self.setDeployTarget('localScrapyd')
        rc = subprocess.call(["scrapyd-deploy", "localScrapyd"], cwd=self.path)
        if rc == 0:
            # self.addToCrontab()
            runp = "/usr/local/bin/runp"
            script = "/usr/local/bin/spiders.py"
            redirect = ">/dev/null 2>&1"
            command = "{} {} crawl:{} {}".format(
                runp, script, self.name, redirect)
            self.ctx.addCronJob(command, self.name, self.cron)
        else:
            msg = "Error registering spiders in scrapyd for {}".format(
                self.name)
            raise __SpidersError__(msg)

    def crawl(self):
        scrapyd = ScrapydAPI(self.ctx.scrapyd_api())
        spiders = scrapyd.list_spiders(self.projectname)
        # payload = {'project': self.projectname}
        # respSpiders = requests.get(listSpidersAPI, params=payload)
        # if respSpiders.status_code == 200:
        #     spiders = respSpiders.json().get('spiders', [])
        if not spiders or len(spiders) < 1:
            msg = "No spider registered in scrapyd for {}".format(
                self.name)
            raise __SpidersError__(msg)
        for spider in spiders:
            jobid = scrapyd.schedule(
                self.projectname,
                spider,
                settings=self.custom_settings,
                **self.custom_args)
            # payload = {'project': self.projectname, 'spider': spider}
            # respSchedule = requests.post(scheduleAPI, data=payload)
            if jobid:
                logging.info("job %s started for project %s, spider %s",
                             jobid,
                             self.projectname,
                             spider)
            else:
                msg = "Scheduling error for project {}, spider {}".format(
                    self.projectname, spider)
                raise __SpidersError__(msg)

    @staticmethod
    def gitRepofromDisk(folder):
        if os.path.isdir(folder):
            g = git.cmd.Git(folder)
            git_remotes = g.remote(verbose=True)
            found = re.search('.*origin[\s\t]+(http[^ ]*)[\s\t]+\(push\).*', git_remotes)
            if found:
                return found.group(1)
            else:
                msg = "Cannot read git remotes from folder {}".format(
                    folder)
                raise IOError(msg)
        else:
            msg = "spider folder {} not found".format(folder)
            raise IOError(msg)

    @staticmethod
    def getProjectName(scrapycfg):
        if os.path.isfile(scrapycfg):
            with open(scrapycfg) as f:
                for line in f:
                    if line.startswith('project = '):
                        return line.split(' = ')[1].strip('\n ')
        else:
            msg = "scrapy.cfg ({}) not found!".format(scrapycfg)
            raise IOError()
        msg = "Cannot find project name from {}".format(scrapycfg)
        raise IOError(msg)


def crawl(*raw_args):
    """
        start job(s) for spider(s) in specified scrapy project
    """
    sCtx = __SpidersCtx__()
    if not sCtx.isScrapydUp():
        raise __SpidersError__("Scrapyd is unreachable")

    def spider(name):
        if name:
            return __ScrapyProject__(sCtx, name)
        raise argparse.ArgumentTypeError('spider name missing')
    parser = argparse.ArgumentParser(
        prog=__name__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('spider', type=spider)
    try:
        args = parser.parse_args(raw_args)
        args.spider.crawl()
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback,
                                  limit=2, file=sys.stdout)
        msg = "Error during scheduling of a job for {}".format(raw_args)
        raise __SpidersError__(msg)
    sys.exit(0)


def initSpiders():
    """
        Validate and register (in scrapyd and crontab)
        the spiders specified in spiders.json
    """
    sCtx = __SpidersCtx__()
    while True:
        logging.warning("initSpiders - Waiting for scrapyd...")
        time.sleep(2)
        if sCtx.isScrapydUp():
            break
    # while not sCtx.isScrapydUp():
    #     logging.warning("initSpiders - Waiting for scrapyd...")
    #     time.sleep(2)
    sCtx.cleanCronTab()
    with open(sCtx.spiders_json(), 'r') as f:
        json_obj = json.load(f)
    # fetch projects
    projects = list()
    try:
        for name in json_obj.get('spiders').keys():
            try:
                projects.append(__ScrapyProject__(sCtx, str(name)))
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_traceback,
                                          limit=2, file=sys.stdout)
                logging.error("initSpiders - Cannot fetch scrapy project data for %s", name)
        nb_proj = len(projects)
        logging.info("initSpiders - %s projects found.", nb_proj)
    except:
        raise __SpidersError__("Cannot read spiders from {} : file empty "
                               "or invalid data structure".format(sCtx.spiders_json()))
    else:
        if nb_proj < 1:
            logging.error("No spider configured in {}".format(sCtx.spiders_json()))
        else:
            # register projects in scrapyd and cron
            for scrapyp in projects:
                try:
                    logging.info("initSpiders - Registering %s", scrapyp.name)
                    scrapyp.registerSpiders()
                except:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    traceback.print_exception(exc_type, exc_value, exc_traceback,
                                              limit=2, file=sys.stdout)
                    msg = "initSpiders - Cannot register spiders "\
                          "for {} in scrapyd and crontab".format(name)
                    logging.error(msg)
        sCtx.printCronJobs()
        logging.info("initSpiders - Finished!")
        sys.exit(0)
