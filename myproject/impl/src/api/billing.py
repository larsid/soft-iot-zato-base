# -*- coding: utf-8 -*-

# Zato
from zato.server.service import Service

class GetBilling(Service):

    name = 'api.billing.get'

    def handle(self):
        self.logger.info('%s has been invoked', self.name)
        self.response.payload = {'Hello': 'Billing'}
