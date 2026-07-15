import type {
  BookingCreatePayload,
  MiniAppAdminBookingCard,
  MiniAppAdminDashboard,
  MiniAppAdminMeetingType,
  MiniAppBooking,
  MiniAppConfig,
  MiniAppMeetingType,
  MiniAppScheduleRestriction,
  MiniAppScheduleSettings,
  MiniAppSlot,
  MiniAppUser,
  MiniAppWorkingHours,
} from "./types";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

type AuthResponse = {
  user: MiniAppUser;
  session_expires_at: string;
};

type BookingListResponse = {
  items: MiniAppBooking[];
};

type BookingDetailResponse = {
  booking: MiniAppBooking;
};

type MeetingTypesResponse = {
  items: MiniAppMeetingType[];
};

type AvailableDatesResponse = {
  items: { date: string }[];
};

type SlotsResponse = {
  items: MiniAppSlot[];
};

type AdminBookingsResponse = {
  items: MiniAppAdminBookingCard[];
};

type AdminMeetingTypesResponse = {
  items: MiniAppAdminMeetingType[];
};

type WorkingHoursResponse = {
  items: MiniAppWorkingHours[];
};

type RestrictionsResponse = {
  items: MiniAppScheduleRestriction[];
};

export async function miniAppAuth(initData: string): Promise<AuthResponse> {
  return request<AuthResponse>("/api/miniapp/auth/telegram", {
    method: "POST",
    body: JSON.stringify({ init_data: initData })
  });
}

export async function loadConfig(): Promise<MiniAppConfig> {
  return request<MiniAppConfig>("/api/miniapp/config");
}

export async function loadProfile(): Promise<MiniAppUser> {
  return request<MiniAppUser>("/api/miniapp/profile");
}

export async function loadBookings(): Promise<MiniAppBooking[]> {
  const response = await request<BookingListResponse>("/api/miniapp/bookings");
  return response.items;
}

export async function acceptConsent(): Promise<void> {
  await request("/api/miniapp/consent", {
    method: "POST",
    body: JSON.stringify({ accepted: true }),
  });
}

export async function loadMeetingTypes(): Promise<MiniAppMeetingType[]> {
  const response = await request<MeetingTypesResponse>("/api/miniapp/meeting-types");
  return response.items;
}

export async function loadAvailableDates(): Promise<string[]> {
  const response = await request<AvailableDatesResponse>("/api/miniapp/available-dates");
  return response.items.map((item) => item.date);
}

export async function loadSlots(params: {
  date: string;
  meetingTypeId: string;
  durationMinutes: number;
}): Promise<MiniAppSlot[]> {
  const search = new URLSearchParams({
    date: params.date,
    meeting_type_id: params.meetingTypeId,
    duration_minutes: String(params.durationMinutes),
  });
  const response = await request<SlotsResponse>(`/api/miniapp/slots?${search.toString()}`);
  return response.items;
}

export async function createBooking(payload: BookingCreatePayload): Promise<MiniAppBooking> {
  const response = await request<BookingDetailResponse>("/api/miniapp/bookings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return response.booking;
}

export async function cancelBooking(bookingId: string, reason: string | null): Promise<MiniAppBooking> {
  const response = await request<BookingDetailResponse>(`/api/miniapp/bookings/${bookingId}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  return response.booking;
}

export async function prepareReschedule(bookingId: string): Promise<MiniAppBooking> {
  const response = await request<BookingDetailResponse>(
    `/api/miniapp/bookings/${bookingId}/reschedule/prepare`,
    { method: "POST" },
  );
  return response.booking;
}

export async function loadAdminDashboard(): Promise<MiniAppAdminDashboard> {
  return request<MiniAppAdminDashboard>("/api/miniapp/admin/dashboard");
}

export async function loadAdminBookings(status?: string): Promise<MiniAppAdminBookingCard[]> {
  const search = status ? `?${new URLSearchParams({ status }).toString()}` : "";
  const response = await request<AdminBookingsResponse>(`/api/miniapp/admin/bookings${search}`);
  return response.items;
}

export async function confirmAdminBooking(
  bookingId: string,
  meetingUrl: string | null,
): Promise<MiniAppAdminBookingCard> {
  return request<MiniAppAdminBookingCard>(`/api/miniapp/admin/bookings/${bookingId}/confirm`, {
    method: "POST",
    body: JSON.stringify({ meeting_url: meetingUrl }),
  });
}

export async function rejectAdminBooking(
  bookingId: string,
  reason: string | null,
): Promise<MiniAppAdminBookingCard> {
  return request<MiniAppAdminBookingCard>(`/api/miniapp/admin/bookings/${bookingId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function loadAdminCalendar(): Promise<MiniAppBooking[]> {
  return request<MiniAppBooking[]>("/api/miniapp/admin/calendar");
}

export async function loadScheduleSettings(): Promise<MiniAppScheduleSettings> {
  return request<MiniAppScheduleSettings>("/api/miniapp/admin/schedule/settings");
}

export async function loadWorkingHours(): Promise<MiniAppWorkingHours[]> {
  const response = await request<WorkingHoursResponse>("/api/miniapp/admin/schedule/working-hours");
  return response.items;
}

export async function loadScheduleRestrictions(fromDate: string): Promise<MiniAppScheduleRestriction[]> {
  const search = new URLSearchParams({ from: fromDate });
  const response = await request<RestrictionsResponse>(
    `/api/miniapp/admin/schedule/restrictions?${search.toString()}`,
  );
  return response.items;
}

export async function addClosedDayRestriction(
  restrictionDate: string,
  adminComment: string | null,
): Promise<void> {
  await request("/api/miniapp/admin/schedule/restrictions/closed-day", {
    method: "POST",
    body: JSON.stringify({ restriction_date: restrictionDate, admin_comment: adminComment }),
  });
}

export async function deleteScheduleRestriction(restrictionId: string): Promise<void> {
  await request(`/api/miniapp/admin/schedule/restrictions/${restrictionId}`, {
    method: "DELETE",
  });
}

export async function loadAdminMeetingTypes(): Promise<MiniAppAdminMeetingType[]> {
  const response = await request<AdminMeetingTypesResponse>("/api/miniapp/admin/meeting-types");
  return response.items;
}

export async function addAdminMeetingType(payload: {
  name: string;
  allowed_durations_minutes: number[];
  is_fixed_duration: boolean;
}): Promise<MiniAppAdminMeetingType> {
  return request<MiniAppAdminMeetingType>("/api/miniapp/admin/meeting-types", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function setAdminMeetingTypeActive(
  meetingTypeId: string,
  isActive: boolean,
): Promise<void> {
  await request(`/api/miniapp/admin/meeting-types/${meetingTypeId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
}

export async function trackMiniAppEvent(
  eventName: string,
  payload: Record<string, unknown> = {}
): Promise<void> {
  await request("/api/miniapp/analytics/event", {
    method: "POST",
    body: JSON.stringify({ event_name: eventName, payload })
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init.headers
    }
  });

  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }

  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body.detail?.message ?? body.detail?.code ?? `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}
