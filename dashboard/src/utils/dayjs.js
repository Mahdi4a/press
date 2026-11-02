import dayjs from 'dayjs/esm';
import relativeTime from 'dayjs/esm/plugin/relativeTime';
import localizedFormat from 'dayjs/esm/plugin/localizedFormat';
import updateLocale from 'dayjs/esm/plugin/updateLocale';
import isToday from 'dayjs/esm/plugin/isToday';
import duration from 'dayjs/esm/plugin/duration';
import utc from 'dayjs/esm/plugin/utc';
import timezone from 'dayjs/esm/plugin/timezone';
import advancedFormat from 'dayjs/plugin/advancedFormat';
import { jalaliPlugin } from './jalali';

dayjs.extend(updateLocale);
dayjs.extend(relativeTime);
dayjs.extend(localizedFormat);
dayjs.extend(isToday);
dayjs.extend(duration);
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(advancedFormat);
// Last, so that it wraps the format of every plugin above
dayjs.extend(jalaliPlugin);

// Datetimes are stored in the system timezone of the server, which the
// dashboard boot sends as window.server_timezone. Frappe Cloud runs on IST.
function serverTimezone() {
	return window.server_timezone || 'Asia/Calcutta';
}

export function dayjsLocal(dateTimeString) {
	let localTimezone = dayjs.tz.guess();
	return dayjs.tz(dateTimeString, serverTimezone()).tz(localTimezone);
}

export function dayjsIST(dateTimeString) {
	return dayjs(dateTimeString).tz(serverTimezone());
}

// Times of day (HH:mm) with no date of their own. Anchoring them to today keeps
// the offset right for timezones that observe DST.
export function timeLocal(serverTime) {
	return convertTimeOfDay(serverTime, serverTimezone(), dayjs.tz.guess());
}

export function timeServer(localTime) {
	return convertTimeOfDay(localTime, dayjs.tz.guess(), serverTimezone());
}

function convertTimeOfDay(time, from, to) {
	const today = dayjs().format('YYYY-MM-DD');
	return dayjs.tz(`${today} ${time}`, from).tz(to).format('HH:mm');
}

export function dayjsFloorToMinutes(d, interval) {
	const minutes = d.minute();
	const floored = Math.floor(minutes / interval) * interval;

	return d.minute(floored).second(0).millisecond(0);
}

export default dayjs;
