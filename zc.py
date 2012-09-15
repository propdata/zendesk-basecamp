from zencamp.common import Config
from zencamp.zendesk import Zendesk

config = Config()
c = config.zendesk()

zd = Zendesk(c['subdomain'], c['username'], c['password'])
print zd.recent_tickets()
