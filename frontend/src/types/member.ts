// ── Stage 6C: Member enrollment API ────────────────────────────────────────

export interface MemberEnrollmentParams {
  service_date?: string
}

export interface MemberEnrollmentResponse {
  member_id: string
  enrolled: boolean
  enrollment_id: number | null
  product_id: number | null
  product_name: string | null
  lob: string | null
  network_id: number | null
  effective_date: string | null
  termination_date: string | null
  as_of_date: string
}
