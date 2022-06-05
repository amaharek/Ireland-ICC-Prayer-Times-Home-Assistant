"""The islamic_prayer_times_ie component."""
from datetime import datetime, timedelta
import json
import logging
import requests

from prayer_times_calculator import PrayerTimesCalculator, exceptions
from requests.exceptions import ConnectionError as ConnError
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
import homeassistant.util.dt as dt_util

from .const import (
    CALC_METHODS,
    CONF_CALC_METHOD,
    DATA_UPDATED,
    DEFAULT_CALC_METHOD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

CONFIG_SCHEMA = vol.Schema(
    vol.All(
        cv.deprecated(DOMAIN),
        {
            DOMAIN: {
                vol.Optional(CONF_CALC_METHOD, default=DEFAULT_CALC_METHOD): vol.In(
                    CALC_METHODS
                ),
            }
        },
    ),
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Import the Islamic Prayer component from config."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )

    return True


async def async_setup_entry(hass, config_entry):
    """Set up the Islamic Prayer Component."""
    client = IslamicPrayerClient(hass, config_entry)

    if not await client.async_setup():
        return False

    hass.data.setdefault(DOMAIN, client)
    return True


async def async_unload_entry(hass, config_entry):
    """Unload Islamic Prayer entry from config_entry."""
    if hass.data[DOMAIN].event_unsub:
        hass.data[DOMAIN].event_unsub()
    hass.data.pop(DOMAIN)
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

def formatTime(timeList):
    return str(timeList[0]).zfill(2) + ':' + str(timeList[1]).zfill(2)



class IslamicPrayerClient:
    """Islamic Prayer Client Object."""

    def __init__(self, hass, config_entry):
        """Initialize the Islamic Prayer client."""
        self.hass = hass
        self.config_entry = config_entry
        self.prayer_times_info = {}
        self.available = True
        self.event_unsub = None

    @property
    def calc_method(self):
        """Return the calculation method."""
        return self.config_entry.options[CONF_CALC_METHOD]

    def get_new_prayer_times(self):
        """Fetch prayer times for today."""
        calc_method = self.calc_method
        _LOGGER.debug(calc_method)
        
        # For standard calculation methods, we use fetch_prayer_times library
        # resp is Dict, sample: {'Fajr': '06:47', 'Sunrise': '08:37', 'Dhuhr': '12:22', 'Asr': '13:53', 'Sunset': '16:07', 'Maghrib': '16:07', 'Isha': '17:57', 'Imsak': '06:37', 'Midnight': '00:22'}
        if calc_method != 'icci':
            calc = PrayerTimesCalculator(
                latitude=self.hass.config.latitude,
                longitude=self.hass.config.longitude,
                calculation_method=self.calc_method,
                date=str(dt_util.now().date()),
            )
            return calc.fetch_prayer_times()
        # For Irish ICC calculation, we get the fill timetable of the year from
        # https://islamireland.ie/api/timetable/ , and parse JSON
        else:
            # Only set midnight to 00:00, if failed to get the value via ISNA
            # standard calculation
            midnight = '00:00'
            try:
                calc = PrayerTimesCalculator(
                    latitude=self.hass.config.latitude,
                    longitude=self.hass.config.longitude,
                    calculation_method='isna',
                    date=str(dt_util.now().date()),
                )
                isna_prayers = calc.fetch_prayer_times()
                #_LOGGER.info("ISNA Prayers: " + str(isna_prayers) + " " + str(type(isna_prayers)))
                midnight = isna_prayers['Midnight']
            except Exception as e:
                _LOGGER.info('Failed to extract midnight from ISNA calculation:' + str(e))
            
            current_month = datetime.today().strftime("%-m")
            current_day = datetime.today().strftime("%-d")
            url = 'https://islamireland.ie/api/timetable/'
            json_resp = None
            try:
                resp = requests.get(url=url, params = {})
                if resp.status_code != requests.codes.ok:
                    _LOGGER.debug('islamireland request failed')
                else:
                    _LOGGER.debug('islamireland was successful')
                json_resp = resp.json()
            except Exception as e:
                _LOGGER.info('islamireland request exception raised, got error:' + str(e))
            if json_resp is not None:
                try:
                    prayers = json_resp['timetable'][current_month][current_day]
                    prayer_times_info = {'Fajr': formatTime(prayers[0]), 
                    'Sunrise': formatTime(prayers[1]),
                    'Dhuhr': formatTime(prayers[2]),
                    'Asr': formatTime(prayers[3]), 
                    'Sunset': formatTime(prayers[4]),
                    'Maghrib': formatTime(prayers[4]),
                    'Isha': formatTime(prayers[5]),
                    'Imsak': formatTime(prayers[4]), 
                    'Midnight': midnight}
                    _LOGGER.debug(prayer_times_info)
                    return prayer_times_info
                except Exception as e:
                    _LOGGER.info('Failed to retrive prayer from ICCI, failed to parse prayers from JSON:' + str(e))
                    return isna_prayers
            else:
                _LOGGER.info('Failed to retrive prayer from ICCI, JSON response is None.')
                return isna_prayers

    async def async_schedule_future_update(self):
        """Schedule future update for sensors.

        Midnight is a calculated time.  The specifics of the calculation
        depends on the method of the prayer time calculation.  This calculated
        midnight is the time at which the time to pray the Isha prayers have
        expired.

        Calculated Midnight: The Islamic midnight.
        Traditional Midnight: 12:00AM

        Update logic for prayer times:

        If the Calculated Midnight is before the traditional midnight then wait
        until the traditional midnight to run the update.  This way the day
        will have changed over and we don't need to do any fancy calculations.

        If the Calculated Midnight is after the traditional midnight, then wait
        until after the calculated Midnight.  We don't want to update the prayer
        times too early or else the timings might be incorrect.

        Example:
        calculated midnight = 11:23PM (before traditional midnight)
        Update time: 12:00AM

        calculated midnight = 1:35AM (after traditional midnight)
        update time: 1:36AM.

        """
        _LOGGER.debug("Scheduling next update for Islamic prayer times")

        now = dt_util.utcnow()

        midnight_dt = self.prayer_times_info["Midnight"]

        if now > dt_util.as_utc(midnight_dt):
            next_update_at = midnight_dt + timedelta(days=1, minutes=1)
            _LOGGER.debug(
                "Midnight is after day the changes so schedule update for after Midnight the next day"
            )
        else:
            _LOGGER.debug(
                "Midnight is before the day changes so schedule update for the next start of day"
            )
            next_update_at = dt_util.start_of_local_day(now + timedelta(days=1))

        _LOGGER.info("Next update scheduled for: %s", next_update_at)

        self.event_unsub = async_track_point_in_time(
            self.hass, self.async_update, next_update_at
        )

    async def async_update(self, *_):
        """Update sensors with new prayer times."""
        try:
            prayer_times = await self.hass.async_add_executor_job(
                self.get_new_prayer_times
            )
            _LOGGER.debug(prayer_times)
            self.available = True
        except (exceptions.InvalidResponseError, ConnError):
            self.available = False
            _LOGGER.debug("Error retrieving prayer times")
            async_call_later(self.hass, 60, self.async_update)
            return

        for prayer, time in prayer_times.items():
            self.prayer_times_info[prayer] = dt_util.parse_datetime(
                f"{dt_util.now().date()} {time}"
            )
        await self.async_schedule_future_update()

        _LOGGER.debug("New prayer times retrieved. Updating sensors")
        async_dispatcher_send(self.hass, DATA_UPDATED)

    async def async_setup(self):
        """Set up the Islamic prayer client."""
        await self.async_add_options()

        try:
            await self.hass.async_add_executor_job(self.get_new_prayer_times)
        except (exceptions.InvalidResponseError, ConnError) as err:
            raise ConfigEntryNotReady from err

        await self.async_update()
        self.config_entry.add_update_listener(self.async_options_updated)

        self.hass.config_entries.async_setup_platforms(self.config_entry, PLATFORMS)

        return True

    async def async_add_options(self):
        """Add options for entry."""
        if not self.config_entry.options:
            data = dict(self.config_entry.data)
            calc_method = data.pop(CONF_CALC_METHOD, DEFAULT_CALC_METHOD)

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=data, options={CONF_CALC_METHOD: calc_method}
            )

    @staticmethod
    async def async_options_updated(hass, entry):
        """Triggered by config entry options updates."""
        if hass.data[DOMAIN].event_unsub:
            hass.data[DOMAIN].event_unsub()
        await hass.data[DOMAIN].async_update()
