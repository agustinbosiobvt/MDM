import { forwardRef, type SelectHTMLAttributes } from 'react'
import { useCountries, useCurrencies, useIncoterms, usePaymentTerms } from '../features/lookups/lookups'

type SelectProps = SelectHTMLAttributes<HTMLSelectElement>

export const CountrySelect = forwardRef<HTMLSelectElement, SelectProps>(function CountrySelect(
  props,
  ref,
) {
  const countries = useCountries()
  return (
    <select ref={ref} {...props}>
      <option value="">Choose…</option>
      {countries.data?.map((c) => (
        <option key={c.code} value={c.code}>
          {c.name} ({c.code})
        </option>
      ))}
    </select>
  )
})

export const CurrencySelect = forwardRef<HTMLSelectElement, SelectProps>(function CurrencySelect(
  props,
  ref,
) {
  const currencies = useCurrencies()
  return (
    <select ref={ref} {...props}>
      <option value="">Choose…</option>
      {currencies.data?.map((c) => (
        <option key={c.code} value={c.code}>
          {c.code} — {c.name}
        </option>
      ))}
    </select>
  )
})

export const PaymentTermSelect = forwardRef<HTMLSelectElement, SelectProps>(function PaymentTermSelect(
  props,
  ref,
) {
  const terms = usePaymentTerms()
  return (
    <select ref={ref} {...props}>
      <option value="">Not set</option>
      {terms.data?.map((t) => (
        <option key={t.code} value={t.code}>
          {t.name} ({t.code})
        </option>
      ))}
    </select>
  )
})

export const IncotermSelect = forwardRef<HTMLSelectElement, SelectProps>(function IncotermSelect(
  props,
  ref,
) {
  const incoterms = useIncoterms()
  return (
    <select ref={ref} {...props}>
      <option value="">Not set</option>
      {incoterms.data?.map((t) => (
        <option key={t.code} value={t.code}>
          {t.code} — {t.name}
        </option>
      ))}
    </select>
  )
})
