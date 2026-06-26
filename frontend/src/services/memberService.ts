import { apiClient } from './apiClient'
import type { MemberEnrollmentParams, MemberEnrollmentResponse } from '@/types/member'

/** GET /api/members/<member_id>/enrollment/ */
export async function getMemberEnrollment(
  memberId: string,
  params?: MemberEnrollmentParams,
): Promise<MemberEnrollmentResponse> {
  const query: Record<string, string> = {}
  if (params?.service_date?.trim()) query.service_date = params.service_date.trim()
  const { data } = await apiClient.get<MemberEnrollmentResponse>(
    `/members/${encodeURIComponent(memberId)}/enrollment/`,
    { params: query },
  )
  return data
}
