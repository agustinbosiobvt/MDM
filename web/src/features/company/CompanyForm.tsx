import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Field, FormError } from '../../components/Field'
import { CountrySelect } from '../../components/CodeSelects'
import { code, eori, isoCountry, optionalText, requiredText } from '../parties/validation'
import type { Company, CompanyInput } from './api'

const schema = z.object({
  code,
  legal_name: requiredText(200, 'Legal name'),
  trade_name: optionalText(200),
  eori,
  country_code: isoCountry,
  tax_registration_number: optionalText(50),
})
type In = z.input<typeof schema>

interface Props {
  company?: Company
  submitLabel: string
  busy: boolean
  error: string | null
  onSubmit: (v: CompanyInput) => void
}

/** Identity fields, shared by "Add company" and "Edit company". */
export function CompanyForm({ company, submitLabel, busy, error, onSubmit }: Props) {
  const form = useForm<In, unknown, CompanyInput>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: company?.code ?? '',
      legal_name: company?.legal_name ?? '',
      trade_name: company?.trade_name ?? '',
      eori: company?.eori ?? '',
      country_code: company?.country_code ?? '',
      tax_registration_number: company?.tax_registration_number ?? '',
    },
  })
  const errors = form.formState.errors

  return (
    <form
      className="stack"
      noValidate
      onSubmit={(e) => {
        void form.handleSubmit(onSubmit)(e)
      }}
    >
      <div className="grid-2">
        <Field label="Code" error={errors.code?.message} hint="Short unique ID, e.g. BVT-ES">
          <input type="text" autoComplete="off" {...form.register('code')} />
        </Field>
        <Field label="Country" error={errors.country_code?.message}>
          <CountrySelect {...form.register('country_code')} />
        </Field>
      </div>
      <Field label="Legal name" error={errors.legal_name?.message}>
        <input type="text" {...form.register('legal_name')} />
      </Field>
      <Field label="Trade name" error={errors.trade_name?.message}>
        <input type="text" {...form.register('trade_name')} />
      </Field>
      <div className="grid-2">
        <Field label="EORI" error={errors.eori?.message}>
          <input type="text" autoComplete="off" {...form.register('eori')} />
        </Field>
        <Field
          label="Tax registration number"
          error={errors.tax_registration_number?.message}
          hint="Optional, as printed on invoices, e.g. TRN 104965266000001"
        >
          <input type="text" autoComplete="off" {...form.register('tax_registration_number')} />
        </Field>
      </div>
      <FormError message={error} />
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {submitLabel}
        </button>
      </div>
    </form>
  )
}
