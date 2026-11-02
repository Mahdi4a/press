// Gregorian <-> Jalali (Solar Hijri) conversion and a dayjs plugin that prints
// dates as Jalali. The algorithm is the one in iran_base.utils.jalali.

const BREAKS = [
	-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192,
	2262, 2324, 2394, 2456, 3178,
];

const MONTHS = [
	'فروردین',
	'اردیبهشت',
	'خرداد',
	'تیر',
	'مرداد',
	'شهریور',
	'مهر',
	'آبان',
	'آذر',
	'دی',
	'بهمن',
	'اسفند',
];

// Index 0 is Sunday, like dayjs
const WEEKDAYS = [
	'یکشنبه',
	'دوشنبه',
	'سه‌شنبه',
	'چهارشنبه',
	'پنجشنبه',
	'جمعه',
	'شنبه',
];

// The localized formats dayjs knows in English, spelled out so that the date
// part can be replaced
const LOCALIZED = {
	LT: 'h:mm A',
	LTS: 'h:mm:ss A',
	L: 'MM/DD/YYYY',
	LL: 'MMMM D, YYYY',
	LLL: 'MMMM D, YYYY h:mm A',
	LLLL: 'dddd, MMMM D, YYYY h:mm A',
	l: 'M/D/YYYY',
	ll: 'MMM D, YYYY',
	lll: 'MMM D, YYYY h:mm A',
	llll: 'ddd, MMM D, YYYY h:mm A',
};

function div(a, b) {
	return ~~(a / b);
}

function mod(a, b) {
	return a - ~~(a / b) * b;
}

function jalCal(jy) {
	let bl = BREAKS.length;
	let gy = jy + 621;
	let leapJ = -14;
	let jp = BREAKS[0];
	let jm;
	let jump = 0;
	for (let i = 1; i < bl; i += 1) {
		jm = BREAKS[i];
		jump = jm - jp;
		if (jy < jm) break;
		leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4);
		jp = jm;
	}
	let n = jy - jp;
	leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
	if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
	let leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
	let march = 20 + leapJ - leapG;
	if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
	let leap = mod(mod(n + 1, 33) - 1, 4);
	if (leap === -1) leap = 4;
	return { leap, gy, march };
}

function g2d(gy, gm, gd) {
	let d =
		div((gy + div(gm - 8, 6) + 100100) * 1461, 4) +
		div(153 * mod(gm + 9, 12) + 2, 5) +
		gd -
		34840408;
	return d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
}

function d2j(jdn) {
	let gy = jdn2g(jdn).gy;
	let jy = gy - 621;
	let r = jalCal(jy);
	let jdn1f = g2d(gy, 3, r.march);
	let k = jdn - jdn1f;
	if (k >= 0) {
		if (k <= 185) {
			return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 };
		}
		k -= 186;
	} else {
		jy -= 1;
		k += 179;
		if (r.leap === 1) k += 1;
	}
	return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
}

function jdn2g(jdn) {
	let j = 4 * jdn + 139361631;
	j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
	let i = div(mod(j, 1461), 4) * 5 + 308;
	let gd = div(mod(i, 153), 5) + 1;
	let gm = mod(div(i, 153), 12) + 1;
	let gy = div(j, 1461) - 100100 + div(8 - gm, 6);
	return { gy, gm, gd };
}

export function toJalali(gy, gm, gd) {
	return d2j(g2d(gy, gm, gd));
}

const pad = (n) => String(n).padStart(2, '0');

// Replace the date tokens of a dayjs format string with the Jalali values of
// d, leaving the time tokens to dayjs
export function jalaliFormat(d, format) {
	const { jy, jm, jd } = toJalali(d.year(), d.month() + 1, d.date());
	const weekday = WEEKDAYS[d.day()];
	const values = {
		YYYY: jy,
		YY: pad(jy % 100),
		MMMM: MONTHS[jm - 1],
		MMM: MONTHS[jm - 1],
		MM: pad(jm),
		M: jm,
		DD: pad(jd),
		D: jd,
		Do: jd,
		dddd: weekday,
		ddd: weekday,
		dd: weekday,
	};
	const expanded = format.replace(
		/\[[^\]]*]|LTS|LT|L{1,4}|l{1,4}/g,
		(token) => LOCALIZED[token] || token,
	);
	return expanded.replace(
		/\[[^\]]*]|YYYY|YY|MMMM|MMM|MM|M|DD|Do|D|dddd|ddd|dd/g,
		(token) => (token[0] === '[' ? token : `[${values[token]}]`),
	);
}

// Formats such as YYYY-MM-DD are sent to the server or used to compare days, so
// only the ones meant to be read (month or weekday names, localized formats)
// turn Jalali
const DISPLAY_FORMAT = /L{1,4}(?!T)|l{2,4}|M{3,4}|d{3,4}/;

function isDisplayFormat(format) {
	return Boolean(format) && DISPLAY_FORMAT.test(format.replace(/\[[^\]]*]/g, ''));
}

export function jalaliPlugin(_option, dayjsClass) {
	const originalFormat = dayjsClass.prototype.format;
	dayjsClass.prototype.format = function (format) {
		if (!window.jalali_dates || !isDisplayFormat(format)) {
			return originalFormat.call(this, format);
		}
		return originalFormat.call(this, jalaliFormat(this, format));
	};
}
