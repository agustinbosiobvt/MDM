import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

export interface CodeName {
  code: string
  name: string
}

// ISO lists change with a migration, never during a session.
export const useCountries = () =>
  useQuery({
    queryKey: ['lookups', 'countries'],
    queryFn: () => api<CodeName[]>('/api/lookups/countries'),
    staleTime: Infinity,
  })

export const usePaymentTerms = () =>
  useQuery({
    queryKey: ['lookups', 'payment-terms'],
    queryFn: () => api<CodeName[]>('/api/lookups/payment-terms'),
    staleTime: Infinity,
  })

export const useIncoterms = () =>
  useQuery({
    queryKey: ['lookups', 'incoterms'],
    queryFn: () => api<CodeName[]>('/api/lookups/incoterms'),
    staleTime: Infinity,
  })

export const usePriceTypes = () =>
  useQuery({
    queryKey: ['lookups', 'price-types'],
    queryFn: () => api<CodeName[]>('/api/lookups/price-types'),
    staleTime: Infinity,
  })

export const useCurrencies = () =>
  useQuery({
    queryKey: ['lookups', 'currencies'],
    queryFn: () => api<CodeName[]>('/api/lookups/currencies'),
    staleTime: Infinity,
  })
