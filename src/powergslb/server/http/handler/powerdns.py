import json
import logging

import netaddr

from powergslb.server.http.handler.abstract import AbstractContentHandler

import powergslb.monitor

__all__ = ['PowerDNSContentHandler']


class PowerDNSContentHandler(AbstractContentHandler):
    """
    PowerDNS content handler
    """

    def _get_lookup(self):
        records = self.database.gslb_records(*self.dirs[2:])
        qtype_records = self._split_records(records)
        filtered_records = self._filter_records(qtype_records)
        result = self._strip_records(filtered_records)

        return {'result': result}

    def _filter_records(self, qtype_records):
        records = []
        for qtype in qtype_records:

            fallback_records = {}
            live_records = {}

            for record in qtype_records[qtype]:
                if record['fallback']:
                    if record['weight'] not in fallback_records:
                        fallback_records[record['weight']] = []

                    fallback_records[record['weight']].append(record)

                if record['id'] not in powergslb.monitor.get_status():
                    if record['weight'] not in live_records:
                        live_records[record['weight']] = []

                    live_records[record['weight']].append(record)

            if live_records:
                filtered_records = live_records[max(live_records)]
            elif fallback_records:
                filtered_records = fallback_records[max(fallback_records)]
            else:
                filtered_records = []

            if not filtered_records:
                continue

            if filtered_records[0]['persistence']:
                records.append(self._remote_ip_persistence(filtered_records))
            else:
                records.extend(filtered_records)

        return records

    def _remote_ip_persistence(self, records):
        ip_value = 0
        remote_ip = self.headers.get('X-Remotebackend-Real-Remote')

        if remote_ip is None:
            logging.error("{}: 'X-Remotebackend-Real-Remote' header missing".format(type(self).__name__))
        else:
            try:
                network = netaddr.IPNetwork(remote_ip)
            except netaddr.AddrFormatError as e:
                logging.error("{}: 'X-Remotebackend-Real-Remote' header invalid: {}: {}".format(
                        type(self).__name__, type(e).__name__, e))
            else:
                if network.version == 4:
                    ip_value = network.ip.value >> records[0]['persistence']
                elif network.version == 6:
                    ip_value = network.ip.value >> records[0]['persistence']

        return records[hash(ip_value) % len(records)]

    def _split_records(self, records):
        qtype_records = {}
        for record in records:
            if record['qtype'] in ['MX', 'SRV']:
                content_split = record['content'].split()
                try:
                    record['priority'] = int(content_split[0])
                    record['content'] = ' '.join(content_split[1:])
                except (KeyError, ValueError) as e:
                    logging.error('{}: record id {} priority missing or invalid: {}: {}'.format(
                            type(self).__name__, record['id'], type(e).__name__, e))
                    continue

            if record['qtype'] not in qtype_records:
                qtype_records[record['qtype']] = []

            qtype_records[record['qtype']].append(record)

        return qtype_records

    @staticmethod
    def _strip_records(records):
        result = []
        for record in records:
            if record['qtype'] in ['MX', 'SRV']:
                names = ['qname', 'qtype', 'content', 'ttl', 'priority']
                values = [record['qname'], record['qtype'], record['content'], record['ttl'], record['priority']]
            else:
                names = ['qname', 'qtype', 'content', 'ttl']
                values = [record['qname'], record['qtype'], record['content'], record['ttl']]

            result.append(dict(zip(names, values)))

        return result

    def content(self):
        if len(self.dirs) == 4 and self.dirs[1] == 'lookup':
            content = self._get_lookup()
        else:
            content = {'result': False}

        return json.dumps(content, separators=(',', ':'))
