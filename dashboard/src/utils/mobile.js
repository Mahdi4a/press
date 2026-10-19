// Accounts created with a mobile number use a placeholder email on the server
// (see press/utils/sms.py), so the login and signup pages convert before calling the API.
export const PHONE_EMAIL_DOMAIN = 'phone.press.local';

const PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹';
const ARABIC_DIGITS = '٠١٢٣٤٥٦٧٨٩';

function toLatinDigits(value) {
	return value.replace(/[۰-۹٠-٩]/g, (ch) => {
		const index = PERSIAN_DIGITS.indexOf(ch);
		return String(index >= 0 ? index : ARABIC_DIGITS.indexOf(ch));
	});
}

// Iranian mobile written as 09123456789, 9123456789, +989123456789 or 00989123456789
const MOBILE_PATTERN = /^(?:\+?98|0098|0)?(9\d{9})$/;

function cleaned(value) {
	return toLatinDigits((value || '').trim()).replace(/[\s-]/g, '');
}

export function isMobileNumber(value) {
	return MOBILE_PATTERN.test(cleaned(value));
}

export function toLoginEmail(value) {
	const typed = (value || '').trim();
	if (!typed || typed.includes('@')) return typed;

	const match = cleaned(typed).match(MOBILE_PATTERN);
	return match ? `0${match[1]}@${PHONE_EMAIL_DOMAIN}` : typed;
}
