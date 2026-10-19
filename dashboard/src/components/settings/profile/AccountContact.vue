<template>
	<Card title="Contact details" class="mx-auto max-w-3xl">
		<div v-if="info.data" class="divide-y">
			<div class="flex items-center justify-between py-3">
				<div>
					<div class="text-base font-medium text-ink-gray-8">Email</div>
					<div class="mt-1 text-sm text-ink-gray-6">
						{{ info.data.email || 'Not added' }}
					</div>
				</div>
				<Button v-if="!info.data.email" @click="openDialog('email')">
					Add email
				</Button>
			</div>
			<div class="flex items-center justify-between py-3">
				<div>
					<div class="text-base font-medium text-ink-gray-8">Mobile number</div>
					<div class="mt-1 text-sm text-ink-gray-6">
						{{ info.data.mobile_no || 'Not added' }}
					</div>
				</div>
				<Button @click="openDialog('mobile')">
					{{ info.data.mobile_no ? 'Change' : 'Add mobile' }}
				</Button>
			</div>
		</div>

		<Dialog
			v-model="show"
			:options="{ title: kind === 'email' ? 'Add email' : 'Add mobile number' }"
		>
			<template #body-content>
				<form
					class="space-y-3"
					@submit.prevent="codeSent ? verify.submit() : sendCode.submit()"
				>
					<FormControl
						:label="kind === 'email' ? 'Email' : 'Mobile number'"
						:placeholder="kind === 'email' ? 'johndoe@mail.com' : '09121234567'"
						:disabled="codeSent"
						v-model="value"
					/>
					<FormControl
						v-if="codeSent"
						label="Verification code"
						placeholder="123456"
						v-model="otp"
					/>
					<ErrorMessage :message="sendCode.error || verify.error" />
					<Button
						class="w-full"
						variant="solid"
						type="submit"
						:loading="sendCode.loading || verify.loading"
					>
						{{ codeSent ? 'Verify' : 'Send verification code' }}
					</Button>
				</form>
			</template>
		</Dialog>
	</Card>
</template>

<script setup>
import { Button, Card, createResource, Dialog, ErrorMessage, FormControl } from 'frappe-ui'
import { ref } from 'vue'
import { toast } from 'vue-sonner'

const show = ref(false)
const kind = ref('email')
const value = ref('')
const otp = ref('')
const codeSent = ref(false)

const info = createResource({
	url: 'press.api.account.get_contact_info',
	auto: true,
})

const sendCode = createResource({
	url: 'press.api.account.request_contact_otp',
	makeParams: () => ({ kind: kind.value, value: value.value }),
	onSuccess() {
		codeSent.value = true
		toast.success('Verification code sent')
	},
})

const verify = createResource({
	url: 'press.api.account.verify_contact_otp',
	makeParams: () => ({ kind: kind.value, value: value.value, otp: otp.value }),
	onSuccess() {
		show.value = false
		toast.success(kind.value === 'email' ? 'Email added' : 'Mobile number saved')
		// Adding the first real email renames the user, so load everything again
		if (kind.value === 'email') window.location.reload()
		else info.reload()
	},
})

function openDialog(type) {
	kind.value = type
	value.value = ''
	otp.value = ''
	codeSent.value = false
	sendCode.error = null
	verify.error = null
	show.value = true
}
</script>
