#!/usr/bin/env python


import re
import commands


# Removes colour codes from the output
STRIP_COLOUR='sed -r "s/\x1B\[([0-9]{1,3}((;[0-9]{1,3})*)?)?[m|K]//g"'

# NB: These commands require the ability to run passenger-memory-stats and
# passenger-status.  You might need to prepend the commands with variations
# on 'rvmsudo' or 'sudo -u username -i' or some other concoction.
PASSENGER_STATUS_CMD = 'sudo passenger-status | ' + STRIP_COLOUR
PASSENGER_MEMORY_STATS_CMD = 'sudo passenger-memory-stats | ' + STRIP_COLOUR


class Passenger:
    def __init__(self, agent_config, checks_logger, raw_config):
        self.agent_config = agent_config
        self.checks_logger = checks_logger
        self.raw_config = raw_config

    def get_passenger_status(self):
        """
        Get passenger status.  Eg,

        Version : 4.0.10
        Date    : 2014-03-31 14:49:29 -0500
        Instance: 2699
        ----------- General information -----------
        Max pool size : 10
        Processes     : 3
        Requests in top-level queue : 0

        ----------- Application groups -----------
        /path/to/rails_app#default:
          App root: /path/to_rails_app
          Requests in queue: 0
          * PID: 1175    Sessions: 0       Processed: 64      Uptime: 3h 42m 28s
            CPU: 0%      Memory  : 89M     Last used: 22m 10s
          * PID: 1225    Sessions: 0       Processed: 67      Uptime: 3h 42m 16s
            CPU: 0%      Memory  : 92M     Last used: 22m 9s a
          * PID: 11801   Sessions: 0       Processed: 61      Uptime: 1h 43m 15s
            CPU: 0%      Memory  : 90M     Last used: 22m 10s

        """
        stats = {
            'max_pool_size': None,
            'processes': None,
            'requests_in_top_queue': None,
            'active_sessions': None,
            'available_pool_size': None,
            'total_processed_count': None
        }
        status, out = commands.getstatusoutput(PASSENGER_STATUS_CMD)
        if status != 0:
            self.checks_logger.error("Failed: %s" % PASSENGER_STATUS_CMD)
            return stats

        match = re.search('Max pool size +: +(\d+)', out)
        if match:
            stats['max_pool_size'] = int(match.group(1))
        self.checks_logger.debug('max_pool_size = %s' %
                stats['max_pool_size'])

        match = re.search('Processes +: +(\d+)', out)
        if match:
            stats['processes'] = int(match.group(1))
        self.checks_logger.debug('processes = %s' %
                stats['processes'])

        match = re.search('Requests in top-level queue +: +(\d+)', out)
        if match:
            stats['requests_in_top_queue'] = int(match.group(1))
        self.checks_logger.debug('requests_in_top_queue = %s' %
                stats['requests_in_top_queue'])

        stats['active_sessions'] = 0
        for session_count in re.findall('Sessions: +(\d+)', out):
            stats['active_sessions'] += int(session_count)
        self.checks_logger.debug('active_sessions = %s' %
                stats['active_sessions'])

        stats['total_processed_count'] = 0
        for processed_count in re.findall('Processed: +(\d+)', out):
            stats['total_processed_count'] += int(processed_count)
        self.checks_logger.debug('total_processed_count = %s' %
                stats['total_processed_count'])

        stats['available_pool_size'] = stats['max_pool_size'] - stats['active_sessions']
        self.checks_logger.debug('available_pool_size = %s' %
                stats['available_pool_size'])

        return stats

    def get_passenger_memory_stats(self):
        """
        Get passenger memory stats.  Eg,

        20998  22.9 MB   0.3 MB   PassengerWatchdog
        21001  126.4 MB  6.8 MB   PassengerHelperAgent
        21016  70.5 MB   0.8 MB   PassengerLoggingAgent
        """
        stats = {
            'passenger_watchdog_rss_mb' : None,
            'passenger_helper_agent_rss_mb' : None,
            'passenger_logging_agent_rss_mb' : None,
            'total_private_dirty_rss_mb' : None,
        }
        status, out = commands.getstatusoutput(PASSENGER_MEMORY_STATS_CMD)
        if status != 0:
            self.checks_logger.error("Failed: %s" % PASSENGER_MEMORY_STATS_CMD)
            return stats

        # Passenger watchdog memory
        match = re.search('\d+ +\d+\.?\d+ MB +(\d+\.?\d+) MB + PassengerWatchdog', out)
        if match:
            stats['passenger_watchdog_rss_mb'] = float(match.group(1))
        self.checks_logger.debug('passenger_watchdog_rss_mb = %s' %
                stats['passenger_watchdog_rss_mb'])

        # Passenger helper agent memory
        match = re.search('\d+ +\d+\.?\d+ MB +(\d+\.?\d+) MB + PassengerHelperAgent', out)
        if match:
            stats['passenger_helper_agent_rss_mb'] = float(match.group(1))
        self.checks_logger.debug('passenger_helper_agent_rss_mb = %s' %
                stats['passenger_helper_agent_rss_mb'])

        # Passenger logging agent memory
        match = re.search('\d+ +\d+\.?\d+ MB +(\d+\.?\d+) MB + PassengerLoggingAgent', out)
        if match:
            stats['passenger_logging_agent_rss_mb'] = float(match.group(1))
        self.checks_logger.debug('passenger_logging_agent_rss_mb = %s' %
                stats['passenger_logging_agent_rss_mb'])

        # There are multiple sections, each with lines that match
        # the regex for totals, so we scan down to the section we're
        # interested in
        in_passenger_processes = False
        for line in out.splitlines():
            # Make sure we jump past the sections about Apache and Nginx,
            # straight to the Passenger section
            if not in_passenger_processes:
                in_passenger_processes = re.match('-+ Passenger processes -+', line)
                continue
            # Total RSS used by passenger and rails processes.  Eg,
            # ### Total private dirty RSS: 2266.23 MB
            total_private_dirty_rss_mb_match = re.match('### Total private dirty RSS: (\d+\.?\d+) MB', line)
            if total_private_dirty_rss_mb_match:
                stats['total_private_dirty_rss_mb'] = float(total_private_dirty_rss_mb_match.group(1))
            self.checks_logger.debug('total_private_dirty_rss_mb = %s' %
                    stats['total_private_dirty_rss_mb'])

        return stats

    def run(self):
        stats = {}
        stats.update(self.get_passenger_status())
        stats.update(self.get_passenger_memory_stats())
        return stats


if __name__ == "__main__":
    import logging
    logger = logging.getLogger("Passenger")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    passenger = Passenger(None, logger, None)
    passenger.run()
