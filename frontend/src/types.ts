export type MiniAppUser = {
  id: string;
  telegram_id: number;
  telegram_username: string | null;
  full_name: string | null;
  email: string | null;
  has_consent: boolean;
  is_blocked: boolean;
  is_admin: boolean;
};

export type MiniAppConfig = {
  timezone: string;
  consent_url: string | null;
  policy_url: string | null;
  mini_app_public_path: string;
};

export type MiniAppMeetingType = {
  id: string;
  name: string;
  allowed_durations_minutes: number[];
  is_fixed_duration: boolean;
};

export type MiniAppAdminMeetingType = MiniAppMeetingType & {
  is_active: boolean;
};

export type MiniAppAdminBookingCard = {
  booking: MiniAppBooking;
  user: MiniAppUser;
  meeting_type: MiniAppMeetingType;
};

export type MiniAppAdminDashboard = {
  metrics: {
    pending: number;
    confirmed: number;
    reschedule_requested: number;
    cancelled: number;
  };
  upcoming: MiniAppBooking[];
  recent_pending: MiniAppBooking[];
};

export type MiniAppScheduleSettings = {
  timezone: string;
  min_booking_lead_days: number;
  booking_horizon_days: number;
  slot_step_minutes: number;
  meeting_buffer_minutes: number;
};

export type MiniAppWorkingHours = {
  weekday: number;
  is_working_day: boolean;
  start_time: string | null;
  end_time: string | null;
};

export type MiniAppScheduleRestriction = {
  id: string;
  restriction_date: string;
  restriction_type: string;
  start_time: string | null;
  end_time: string | null;
  admin_comment: string | null;
};

export type MiniAppSlot = {
  starts_at: string;
  ends_at: string;
  label: string;
};

export type MiniAppBooking = {
  id: string;
  status: string;
  meeting_type_id: string;
  duration_minutes: number;
  starts_at: string;
  ends_at: string;
  user_comment: string | null;
  rejection_reason: string | null;
  cancellation_reason: string | null;
  reserved_until: string | null;
  meeting_url: string | null;
  is_reschedule_request: boolean;
  previous_booking_id: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type BookingCreatePayload = {
  full_name: string;
  email: string;
  meeting_type_id: string;
  duration_minutes: number;
  starts_at: string;
  ends_at: string;
  user_comment: string | null;
  previous_booking_id: string | null;
};

export type AuthState =
  | { status: "loading" }
  | { status: "preview"; config: MiniAppConfig | null; user: MiniAppUser }
  | { status: "ready"; config: MiniAppConfig | null; user: MiniAppUser }
  | { status: "error"; message: string };

export type TelegramTheme = "light" | "dark";
