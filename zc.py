from zencamp.common import Config
from zencamp.zendesk import Zendesk
from zencamp.basecamp import Basecamp

from datetime import date, datetime, timedelta
from os import path

import logging
import pickle
import sys


# Helpers
class ProcessLog(object):
    def __init__(self):
        if not path.exists("processed.pkl"):
            self.processed = []
        else:
            f = open('processed.pkl', 'rb')
            self.processed = pickle.load(f)
            f.close()

    def get_processed(self):
        return [p['id'] for p in self.processed]

    def add_processed(self, id):
        self.processed.append({'id': id, 'date': datetime.now()})
        f = open('processed.pkl', 'wb')
        pickle.dump(self.processed, f, True)
        f.close()


# Configure logging
FORMAT = "%(asctime)-15s - %(levelname)8s - %(module)s - %(message)s"
logging.basicConfig(format=FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.info("Starting Zendesk <-> Basecamp sync")

# Get configuration
config = Config()
logger.debug("Getting Zendesk configuration...")
zc = config.zendesk()
logger.debug("Zendesk configuration: " + ", ".join("%s(%s)" % (
    a, getattr(zc, a)) for a in dir(zc) if not a.startswith("_")))
bc = config.basecamp()
logger.debug("Basecamp configuration: " + ", ".join("%s(%s)" % (
    a, getattr(bc, a)) for a in dir(bc) if not a.startswith("_")))
process_log = ProcessLog()

# Stage 1 - Zendesk -> Basecamp
# Grab all recent tickets from zendesk
zdi = Zendesk(zc.subdomain, zc.username, zc.password)
logger.info("Connecting to Zendesk and requesting recent ticket list.")
recent_tickets = zdi.recent_tickets()
all_groups = zdi.list_groups()
GROUPS = {'Feeds': None, 'L3 Support': None}
for g in all_groups:
    if g['name'] in GROUPS:
        GROUPS[g['name']] = g['id']

# This contains the list of tickets we are interested in sending to Basecamp
queue = []

# This comes from a pickle file containing our /already processed/ list
ALREADY_PROCESSED = process_log.get_processed()

for rt in recent_tickets['tickets']:
    if rt['status'] in ('new', 'open'):
        logger.debug("Ticket #%d - %s" % (rt['id'], rt['subject']))
        for grp, gid in GROUPS.items():
            if rt['group_id'] == gid:
                # At this point we have new | open tickets in our groups
                if rt['id'] not in ALREADY_PROCESSED:
                    logger.info("Adding ticket #%d to queue" % rt['id'])
                    queue.append(rt)

logger.info("%d tickets to process." % len(queue))

# Bail out if there is nothing to process
if len(queue) < 1:
    logger.info("Nothing to process, exiting.")
    sys.exit(0)

# Login to Basecamp and find Backlog project
bci = Basecamp(bc.basecamp_id, bc.username, bc.password)
logger.info("Connecting to Basecamp and requesting project list.")
bc_projects = bci.list_projects()
bc_project = None
for bp in  bc_projects:
    if bp['name'] == bc.project:
        bc_project = bp

if bc_project:
    logger.info("Found project '%(name)s' (id: %(id)d)" % (bc_project))
else:
    logger.fatal("Couldn't find project named '%s'" % bc.project)
    sys.exit(1)

todo_list = None
todo_list_name = date.today().strftime(bc.todo_list)

logger.info("Searching for todo list %s..." % todo_list_name)
# Check for Todo List
for bc_todo_list in bci.list_todo_lists(project_id=bc_project['id']):
    if bc_todo_list['name'] == todo_list_name:
        todo_list = bc_todo_list
        logger.info("Found matching todo list, appending todo...")

# Create Todo List if it doesn't exist
if not todo_list:
    logger.info("Couldn't find matching todo list, creating it...")
    todo_list_uri = bci.create_todo_list(project_id=bc_project['id'], data={
        'name': todo_list_name,
        'description': "Zendesk Syndication Support"})
    tdid = todo_list_uri.split('/todolists/')[1].split('-')[0]
    todo_list = bci.get_todo_list(project_id=bc_project['id'],
            todo_list_id=tdid)

for bc_ticket in queue:
    logger.info("Processing Zendesk ticket #%s..." % bc_ticket['id'])

    # Add todo to todo_list
    two_days = str(date.today() + timedelta(days=2))
    todo_data = {
        'content': '#%s - %s (Priority: %s) [?]' % (bc_ticket['id'],
            bc_ticket['subject'], bc_ticket['priority']),
        'due_at': two_days,
        'assignee': {
            'id': bc.auto_assign_to,
            'type': 'Person'
        }
    }
    logger.info("Creating todo in Basecamp...")
    todo_uri = bci.create_todo(project_id=bc_project['id'],
            todo_list_id=todo_list['id'], data=todo_data)

    # Add comment containing ticket request info
    todo_id = todo_uri.split('/todos/')[1].split('-')[0]
    todo_comment_data = {
        "content": bc_ticket['description'],
        "subscribers": []
    }
    logger.info("Adding ticket request as comment...")
    comment_uri = bci.create_todo_comment(project_id=bc_project['id'],
            todo_id=todo_id, data=todo_comment_data)

    # Add ticket id to processed history
    process_log.add_processed(bc_ticket['id'])

# Stage 2 - Basecamp -> Zendesk
# Loop through Basecamp todos in Backlog and Current Sprint, find todos we
# submitted. If they're closed, take last comment and append it to zendesk
# ticket, notify assignee of update.
