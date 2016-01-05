import sys
import os
from getpass import getpass
from argparse import ArgumentParser
from datetime import datetime, timedelta

import asana
import json

class Config:
    def __init__(self, config_filename):
        config_file = open(config_filename, 'r')
        config = json.load(config_file)
        self.template_name_pattern = config['template-name-pattern']
        self.weeks_per_schedule = config['weeks-per-schedule']
        self.generated_name_pattern = config['generated-name-pattern']

def generate_schedule(token, config, group, absolute_start_date):
    # create a client
    client = asana.Client.access_token(token)

    # get all projects in the personal workspace
    print('Getting all projects in your Personal Projects workspace ...'),
    sys.stdout.flush()
    me = client.users.me()
    workspace = next(workspace['id'] for workspace in me['workspaces'] if workspace['name'] == 'Personal Projects')
    projects = client.projects.find_by_workspace(workspace, iterator_type=None)
    print('Done')

    # copy each week's template
    for i in range(config.weeks_per_schedule):
        number = i + 1
        start_date = absolute_start_date + timedelta(days=(i * 7))
        end_date = start_date + timedelta(days=6)
        print('\nWeek %d / %d' % (number, config.weeks_per_schedule))

        template_name = config.template_name_pattern % \
            { 'number': number }
        target_name = config.generated_name_pattern % \
            {
                'number': number,
                'group': group,
                'year': start_date.year,
                'month_start': start_date.month,
                'month_end': end_date.month,
                'day_start': start_date.day,
                'day_end': end_date.day
            }
        copy_template(client, workspace, projects, end_date, template_name, target_name)

def copy_template(client, workspace, projects, end_date, template_name, target_name):
    # find the template project
    template_projects = [project for project in projects if project['name'] == template_name]
    if not template_projects:
        print("Could not find template project: %s" % template_name)
        sys.exit(1)
    if len(template_projects) > 1:
        print("More than one matching template project: %s" % template_name)
        sys.exit(1)
    template_project = template_projects[0]

    # check for an already-generated target project
    target_projects = [project for project in projects if project['name'] == target_name]
    if target_projects:
        print("Found an existing target project: %s" % target_name)
        sys.exit(1)

    # generate the target project
    print("Generating new project: %s ..." % target_name),
    sys.stdout.flush()
    target_project = client.projects.create_in_workspace(workspace, { 'name': target_name })
    print('Done')

    # fetch task data from template
    print('Fetching task data ...'),
    sys.stdout.flush()
    tasks = client.tasks.find_by_project(
        template_project['id'],
        {'opt_fields': 'this.name,this.notes,this.projects'},
        limit=100,
        iterator_type=None)
    print('Done')

    # not sure how to check for pagination
    assert(len(tasks) < 100)

    # transform read data to create data, add fields, etc
    print('Copying tasks ...'),
    sys.stdout.flush()
    due_date = end_date
    tasks.reverse()
    for task in tasks:
        # remove template project
        task['projects'] = [project for project in task['projects'] if project['id'] != template_project['id']]

        # reformat...
        for i in range(len(task['projects'])):
            task['projects'][i] = task['projects'][i]['id']

        # add target project
        task['projects'].insert(0, target_project['id'])

        # set due date, or increment if we're at a section header
        # couldn't get task reordering to work, so just creating in reverse
        if task['name'].endswith(':'):
            due_date -= timedelta(days=1)
        else:
            task['due_on'] = "%d-%02d-%02d" % (due_date.year, due_date.month, due_date.day)

        # insert
        new_task = client.tasks.create_in_workspace(workspace, task)
    print('Done')

if __name__ == '__main__':
    # parse args
    parser = ArgumentParser()
    parser.add_argument('-c', '--config', required=True, help='config file')
    parser.add_argument('-g', '--group', required=True, help='group letter')
    parser.add_argument('-s', '--start-date', required=True, help='initial date in MM/DD/YYYY format')
    args = parser.parse_args()

    config = Config(args.config)
    group = args.group
    start_date = datetime.strptime(args.start_date, '%m/%d/%Y')

    if start_date.weekday() != 0:
        print('Start date must be a Monday')
        sys.exit(1)

    token = getpass('Personal Access Token: ')
    if not token:
        print('Must supply Personal Access Token')
        sys.exit(1)
    
    generate_schedule(token, config, group, start_date)

    print('\nScript finished. Make sure you change the default views, add colors, and add to favorites.')
