# scrapyd-docker

[![Current tag](http://img.shields.io/github/tag/gp3t1/scrapyd-docker.svg)](https://github.com/gp3t1/scrapyd-docker/tags) [![Repository issues](http://issuestats.com/github/gp3t1/scrapyd-docker/badge/issue)](http://issuestats.com/github/gp3t1/scrapyd-docker)

[Scrapyd](https://github.com/scrapy/scrapyd) docker image

* loads spiders(http crawlers) from local/git [scrapy](http://scrapy.org/) projects
* customize spiders scheduling with cron syntax
* files produced by exporters are exposed through http

## Installation

* Install docker
	

## Usage

Here's a short explanation how to use `scrapyd-docker`:

* in your scrapy project `settings.py`,
	* define `EXPORT_PATH` (e.g. `EXPORT_PATH = "/tmp/export"`)
	* configure your exporters to write files in `EXPORT_PATH` folder (`settings.get('EXPORT_PATH')`)
	* when deployed to scrapyd, the scheduler will override this setting to make sure all exported files are stored in the correct http folder

* Print the help :
		
		docker run --rm <gp3t1/scrapyd[:tag]> help

* Run or create the container with the following command:

		docker <create|run [--rm] [-d] ...>
		    -v </host/path/to/scrapyd/config>:/etc/scrapyd/
		    -v </host/path/to/scrapyd/data>:/var/lib/scrapyd/
		    -v </host/path/to/logs>:var/log/supervisor/
		    -e SCRAPYD_USER=<scrapyd_user>
		    -p <http_port>:8000
		   [-p <scrapyd_api_port>:6800]
		    --name <my-scrapyd>
		    <gp3t1/scrapyd[:tag]>
		    <scrapyd|help>

	* `<create|run [--rm] [-d] ...>`: see [docker run reference](https://docs.docker.com/engine/reference/run/)
	* `</host/path/to/scrapyd/config>`: your host path mapped to `scrapyd config volume`
	* `</host/path/to/scrapyd/data>`: your host path mapped to `scrapyd data volume`(populated with scrapyd logs, scrapy projects, exported files)
	* `</host/path/to/logs>`: your host path mapped to `supervisor logs volume`
	* `<scrapyd_user>`: start scrapyd as `scrapyd_user` (default='scrapyd')
	* `<http_port>`: available TCP port on your host mapped to `scrapyd exported files`
	* `<scrapyd_api_port>`: available TCP port on your host mapped to `scrapyd api` (not recommended)
	* `--name <my-scrapyd>`: name of the container to build
	* `<gp3t1/scrapyd[:tag]>`: image name (and tag) to build from
	* `<scrapyd|help>`: scrapyd container command. `scrapyd` launch scrapyd, the scheduler and the http server. `help` print the help

* Configure your spiders
	* Spiders configuration file is found in your `scrapyd data volume`/spiders/spiders.json (create it before running the container or modify it after)
		format of the file:

			{
				"spiders": {
					"<your-spider-id/name-from-git>":{
						"giturl":"https://path/to/your/scrapy-repo.git",
						"cron":"0 * * * *",
						"custom_settings":{},
						"custom_args":{}
					},
					"<another-spider-id/name-from-local>":{
						"cron":"0 8 * * 0,6",
						"custom_settings":{},
						"custom_args":{}
					}
				}
			}

		* `<your-spider-id/name>`: must be a valid linux folder name. It will be used to store/read your spidere in `scrapyd data volume`/spiders/`<your-spider-id/name>`
		* `giturl`: don't use it if you want scrapyd to laod your spider from `scrapyd data volume`/spiders/`<your-spider-id/name>`
		* `cron`: standard cron syntax used for your spider scheduling see [crontab.guru](http://crontab.guru/) for help
		* `custom_settings`: will be passed to scrapyd to override project settings during scheduling
		* `custom_args`: will be passed to scrapyd as arguments during scheduling

* Administration
	*	use `docker <start|stop|restart|kill|logs> <my-scrapyd>`. see [docker command line](https://docs.docker.com/engine/reference/commandline/cli/)
	* scrapyd configuration can be found in `scrapyd config volume` (for stability, some settings, like urls and paths, are forced during startup)
	* logs can be found in `scrapyd data volume`/logs and `supervisor logs volume`
	* the http folder containing exported files can be found in `scrapyd data volume`/spiders
	* use `docker exec -ti <my-scrapyd> /bin/sh` to get a terminal from your running container
	* In order to reload spiders configuration, you can
		- restart the container 
		- restart the applications of the container with `docker kill -s SIGHUP <my-scrapyd>`
		- inside the container, execute `supervisorctl start initSpiders`
	* if you need to schedule a job manually, run `su - <scrapyd_user> -c "runp /usr/local/bin/spiders.py crawl:<spider-id/name>"` from inside the container
	
## Contributing

1. Fork it
2. Create your feature branch: `git checkout -b feature/my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin feature/my-new-feature`
5. Submit a pull request

## Requirements / Dependencies

* [docker engine](https://docs.docker.com/engine/installation/) > 1.10

## Version

0.1.0

## License

Copyright (C) <year> <name of author>

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program.  If not, see <http://www.gnu.org/licenses/>.