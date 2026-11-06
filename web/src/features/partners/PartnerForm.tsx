import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Field, FormError } from '../../components/Field'
import {
  CountrySelect,
  CurrencySelect,
  IncotermSelect,
  PaymentTermSelect,
} from '../../components/CodeSelects'
import { code, eori, isoCountry, isoCurrency, optionalText, requiredText } from '../parties/validation'
import type { Partner, PartnerInput } from './api'
import { STATUS_LABELS, type PartnerConfig } from './config'

const optionalCode = z.string().transform((v) => (v === '' ? null : v))

const optionalInt = (min: number, max: number, label: string) =>
  z
    .string()
    .trim()
    .transform((v) => (v === '' ? null : Number(v)))
    .pipe(
      z
        .number({ message: `${label} must be a whole number` })
        .int(`${label} must be a whole number`)
        .min(min, `${label} must be at least ${String(min)}`)
        .max(max, `${label} must be at most ${String(max)}`)
        .nullable(),
    )

const schema = z.object({
  code,
  legal_name: requiredText(200, 'Legal name'),
  trade_name: optionalText(200),
  eori,
  country_code: isoCountry,
  default_currency: isoCurrency,
  status: z.enum(['active', 'on_hold', 'blocked']),
  payment_term_code: optionalCode,
  incoterm_code: optionalCode,
  lead_time_days: optionalInt(0, 730, 'Lead time'),
})
type In = z.input<typeof schema>
type Out = z.output<typeof schema>

interface Props {
  cfg: PartnerConfig
  partner?: Partner
  submitLabel: string
  busy: boolean
  error: string | null
  onSubmit: (v: PartnerInput) => void
}

/** Identity + status + trading terms, shared by customers and vendors (add and edit). */
export function PartnerForm({ cfg, partner: p, submitLabel, busy, error, onSubmit }: Props) {
  const form = useForm<In, unknown, Out>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: p?.code ?? '',
      legal_name: p?.legal_name ?? '',
      trade_name: p?.trade_name ?? '',
      eori: p?.eori ?? '',
      country_code: p?.country_code ?? '',
      default_currency: p?.default_currency ?? 'EUR',
      status: p?.status ?? 'active',
      payment_term_code: p?.payment_term_code ?? '',
      incoterm_code: p?.incoterm_code ?? '',
      lead_time_days: p?.lead_time_days != null ? String(p.lead_time_days) : '',
    },
  })
  const errors = form.formState.errors

  const submit = (v: Out) => {
    // Send only the fields this kind of partner has.
    const { eori: e, lead_time_days, ...common } = v
    onSubmit({
      ...common,
      ...(cfg.hasEori ? { eori: e } : {}),
      ...(cfg.hasLeadTime ? { lead_time_days } : {}),
    })
  }

  return (
    <form
      className="stack"
      noValidate
      onSubmit={(e) => {
        void form.handleSubmit(submit)(e)
      }}
    >
      <div className="grid-2">
        <Field label="Code" error={errors.code?.message} hint="Short unique ID, e.g. AMZ-MX">
          <input type="text" autoComplete="off" {...form.register('code')} />
        </Field>
        <Field label="Status" error={errors.status?.message}>
          <select {...form.register('status')}>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Legal name" error={errors.legal_name?.message}>
        <input type="text" {...form.register('legal_name')} />
      </Field>
      <Field label="Trade name" error={errors.trade_name?.message}>
        <input type="text" {...form.register('trade_name')} />
      </Field>
      {cfg.hasEori && (
        <Field label="EORI" error={errors.eori?.message}>
          <input type="text" autoComplete="off" {...form.register('eori')} />
        </Field>
      )}
      <div className="grid-2">
        <Field label="Country" error={errors.country_code?.message}>
          <CountrySelect {...form.register('country_code')} />
        </Field>
        <Field label="Default currency" error={errors.default_currency?.message}>
          <CurrencySelect {...form.register('default_currency')} />
        </Field>
      </div>
      <div className="grid-2">
        <Field label="Payment terms" error={errors.payment_term_code?.message}>
          <PaymentTermSelect {...form.register('payment_term_code')} />
        </Field>
        <Field label="Incoterm" error={errors.incoterm_code?.message}>
          <IncotermSelect {...form.register('incoterm_code')} />
        </Field>
      </div>
      {cfg.hasLeadTime && (
        <Field label="Lead time (days)" error={errors.lead_time_days?.message}>
          <input type="number" inputMode="numeric" min={0} max={730} {...form.register('lead_time_days')} />
        </Field>
      )}
      <FormError message={error} />
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {submitLabel}
        </button>
      </div>
    </form>
  )
}
