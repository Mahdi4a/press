<template>
	<div>
		<span class="mt-2.5 inline-flex gap-2 text-base text-ink-gray-7">
			<FeatherIcon name="info" class="my-1 h-4" />
			<span class="leading-5">
				You will be redirected to Zarinpal to pay with any Iranian bank card.
				Your balance is updated as soon as the payment is confirmed.
			</span>
		</span>
		<ErrorMessage class="mt-3" :message="createPayment.error" />
		<div class="mt-8">
			<Button
				class="w-full"
				size="md"
				variant="solid"
				label="Proceed to payment using Zarinpal"
				:loading="createPayment.loading"
				@click="createPayment.submit()"
			/>
		</div>
	</div>
</template>
<script setup>
import { Button, createResource, ErrorMessage, FeatherIcon } from 'frappe-ui'
import { DashboardError } from '../../utils/error'

const props = defineProps({
	amount: {
		type: Number,
		default: 0,
	},
	minimumAmount: {
		type: Number,
		default: 0,
	},
})

const createPayment = createResource({
	url: 'press.api.regional_payments.zarinpal.utils.create_payment',
	makeParams() {
		return { amount: props.amount }
	},
	validate() {
		if (!props.amount || props.amount < props.minimumAmount) {
			throw new DashboardError(`Amount must be at least ${props.minimumAmount}`)
		}
	},
	onSuccess(gatewayUrl) {
		window.location.href = gatewayUrl
	},
})
</script>
