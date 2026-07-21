import {
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";

import {
  acceptConsent,
  addAdminMeetingType,
  addClosedDayRestriction,
  addTimeIntervalRestriction,
  cancelAdminBooking,
  cancelBooking,
  confirmAdminBooking,
  createBooking,
  deleteScheduleRestriction,
  loadAdminBookings,
  loadAdminDashboard,
  loadAdminMeetingTypes,
  loadAvailableDates,
  loadBookings,
  loadConfig,
  loadGoogleOAuthStatus,
  loadMeetingTypes,
  loadProfile,
  loadScheduleRestrictions,
  loadScheduleSettings,
  loadSlots,
  loadWorkingHours,
  miniAppAuth,
  rejectAdminBooking,
  setAdminMeetingTypeActive,
  startGoogleOAuth,
  trackMiniAppEvent,
  updateScheduleSettings,
  updateWorkingHours,
} from "./api";
import { initTelegramShell, telegramApp } from "./telegram";
import type { ReactNode } from "react";
import type {
  AuthState,
  BookingCreatePayload,
  MiniAppAdminBookingCard,
  MiniAppAdminDashboard,
  MiniAppAdminMeetingType,
  MiniAppBooking,
  MiniAppConfig,
  MiniAppGoogleOAuthStatus,
  MiniAppMeetingType,
  MiniAppScheduleRestriction,
  MiniAppScheduleSettings,
  MiniAppScheduleSettingsUpdate,
  MiniAppSlot,
  MiniAppUser,
  MiniAppWorkingHours,
  MiniAppWorkingHoursUpdate,
} from "./types";

type TabId = "home" | "calendar" | "admin";
type FormStep = "details" | "slot" | "review";
type DateViewMode = "month" | "time";
type ToastTone = "success" | "error" | "info";
type Toast = { tone: ToastTone; text: string } | null;
type AdminStatusFilter = "" | "pending" | "confirmed" | "reschedule_requested" | "cancelled_by_user" | "rejected";
type AdminView = "requests" | "schedule" | "types";
type AdminScheduleSettingKey = keyof MiniAppScheduleSettingsUpdate;

type BookingFormState = {
  fullName: string;
  email: string;
  meetingTypeId: string;
  durationMinutes: number;
  date: string;
  slotKey: string;
  comment: string;
  previousBookingId: string | null;
};

type Tab = {
  id: TabId;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
};

const tabs: Tab[] = [
  { id: "home", label: "Запись", icon: LayoutDashboard },
  { id: "calendar", label: "Заявки", icon: CalendarDays },
  { id: "admin", label: "Админ", icon: ShieldCheck, adminOnly: true },
];

const MAX_ACTIVE_BOOKINGS = 10;

const previewUser: MiniAppUser = {
  id: "preview",
  telegram_id: 0,
  telegram_username: "preview",
  full_name: "Ирина",
  email: "client@example.com",
  has_consent: false,
  is_blocked: false,
  is_admin: false,
};

const previewMeetingTypes: MiniAppMeetingType[] = [
  {
    id: "preview-consultation",
    name: "Консультация",
    allowed_durations_minutes: [30, 60, 90],
    is_fixed_duration: false,
  },
  {
    id: "preview-diagnostics",
    name: "Диагностика",
    allowed_durations_minutes: [60],
    is_fixed_duration: true,
  },
];

const emptyForm: BookingFormState = {
  fullName: "",
  email: "",
  meetingTypeId: "",
  durationMinutes: 60,
  date: "",
  slotKey: "",
  comment: "",
  previousBookingId: null,
};

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });
  const [activeTab, setActiveTab] = useState<TabId>("home");
  const [bookings, setBookings] = useState<MiniAppBooking[]>([]);
  const [meetingTypes, setMeetingTypes] = useState<MiniAppMeetingType[]>([]);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [availableSlotDates, setAvailableSlotDates] = useState<string[]>([]);
  const [slots, setSlots] = useState<MiniAppSlot[]>([]);
  const [form, setForm] = useState<BookingFormState>(emptyForm);
  const [formStep, setFormStep] = useState<FormStep>("details");
  const [personalDataConsentChecked, setPersonalDataConsentChecked] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [adminView, setAdminView] = useState<AdminView>("requests");
  const [adminStatusFilter, setAdminStatusFilter] = useState<AdminStatusFilter>("pending");
  const [adminDashboard, setAdminDashboard] = useState<MiniAppAdminDashboard | null>(null);
  const [adminBookings, setAdminBookings] = useState<MiniAppAdminBookingCard[]>([]);
  const [selectedAdminCard, setSelectedAdminCard] = useState<MiniAppAdminBookingCard | null>(null);
  const [adminMeetingUrl, setAdminMeetingUrl] = useState("");
  const [adminRejectReason, setAdminRejectReason] = useState("");
  const [scheduleSettings, setScheduleSettings] = useState<MiniAppScheduleSettings | null>(null);
  const [workingHours, setWorkingHours] = useState<MiniAppWorkingHours[]>([]);
  const [restrictions, setRestrictions] = useState<MiniAppScheduleRestriction[]>([]);
  const [newClosedDay, setNewClosedDay] = useState("");
  const [newClosedDayComment, setNewClosedDayComment] = useState("");
  const [newClosedHoursDate, setNewClosedHoursDate] = useState("");
  const [newClosedHoursStart, setNewClosedHoursStart] = useState("");
  const [newClosedHoursEnd, setNewClosedHoursEnd] = useState("");
  const [newClosedHoursComment, setNewClosedHoursComment] = useState("");
  const [adminMeetingTypes, setAdminMeetingTypes] = useState<MiniAppAdminMeetingType[]>([]);
  const [googleOAuthStatus, setGoogleOAuthStatus] = useState<MiniAppGoogleOAuthStatus | null>(null);
  const [newMeetingTypeName, setNewMeetingTypeName] = useState("");
  const [newMeetingTypeDurations, setNewMeetingTypeDurations] = useState("60");

  const isPreview = auth.status === "preview";
  const user = auth.status === "ready" || auth.status === "preview" ? auth.user : null;
  const config = auth.status === "ready" || auth.status === "preview" ? auth.config : null;

  useEffect(() => {
    initTelegramShell();
    void bootstrap();
  }, []);

  useEffect(() => {
    if (auth.status !== "ready") {
      return;
    }
    void trackMiniAppEvent("screen_opened", { screen: activeTab });
  }, [activeTab, auth.status]);

  useEffect(() => {
    if (!form.meetingTypeId || !form.durationMinutes || auth.status === "loading") {
      setAvailableSlotDates([]);
      return;
    }
    void refreshAvailableDates();
  }, [form.meetingTypeId, form.durationMinutes, auth.status]);

  useEffect(() => {
    if (!form.meetingTypeId || !form.durationMinutes || !availableDates.length || auth.status === "loading") {
      setAvailableSlotDates([]);
      return;
    }

    let cancelled = false;
    setAvailableSlotDates([]);

    async function refreshDatesWithSlots() {
      try {
        const checkedDates = await Promise.all(
          availableDates.map(async (date) => {
            const daySlots = isPreview
              ? previewSlots(date)
              : await loadSlots({
                  date,
                  meetingTypeId: form.meetingTypeId,
                  durationMinutes: form.durationMinutes,
                });
            return daySlots.length ? date : null;
          }),
        );
        if (cancelled) {
          return;
        }
        const nextDates = checkedDates.filter((date): date is string => Boolean(date));
        setAvailableSlotDates(nextDates);
      } catch (error) {
        if (!cancelled) {
          setAvailableSlotDates([]);
          showToast("error", errorText(error));
        }
      }
    }

    void refreshDatesWithSlots();
    return () => {
      cancelled = true;
    };
  }, [availableDates, auth.status, form.durationMinutes, form.meetingTypeId, isPreview]);

  useEffect(() => {
    if (!form.date || !availableSlotDates.length || availableSlotDates.includes(form.date)) {
      return;
    }
    setForm((current) => ({ ...current, date: "", slotKey: "" }));
    setSlots([]);
  }, [availableSlotDates, form.date]);

  useEffect(() => {
    if (!form.meetingTypeId || !form.durationMinutes || !form.date || auth.status === "loading") {
      return;
    }
    void refreshSlots();
  }, [form.meetingTypeId, form.durationMinutes, form.date, auth.status]);

  useEffect(() => {
    if (activeTab !== "admin" || !user?.is_admin) {
      return;
    }
    void refreshAdminData();
  }, [activeTab, adminStatusFilter, user?.is_admin]);

  async function bootstrap() {
    try {
      const loadedConfig = await loadConfig().catch(() => null);
      const app = telegramApp();
      const initData = app?.initData;

      if (!initData) {
        const previewBookingsData = previewBookings();
        const previewAvailableDates = previewDates();
        setBookings(previewBookingsData);
        setMeetingTypes(previewMeetingTypes);
        setAvailableDates(previewAvailableDates);
        setAvailableSlotDates(previewAvailableDates);
        setAuth({ status: "preview", config: loadedConfig, user: previewUser });
        setForm((current) => ({
          ...current,
          fullName: previewUser.full_name || "",
          email: previewUser.email || "",
          meetingTypeId: previewMeetingTypes[0].id,
          durationMinutes: previewMeetingTypes[0].allowed_durations_minutes[1],
        }));
        return;
      }

      const authResponse = await miniAppAuth(initData);
      const profile = await loadProfile().catch(() => authResponse.user);
      const [currentBookings, loadedTypes] = await Promise.all([
        loadBookings().catch(() => []),
        loadMeetingTypes().catch(() => []),
      ]);
      setBookings(currentBookings);
      setMeetingTypes(loadedTypes);
      setAuth({ status: "ready", config: loadedConfig, user: profile });
      setPersonalDataConsentChecked(profile.has_consent);
      setForm((current) => ({
        ...current,
        fullName: profile.full_name || "",
        email: profile.email || "",
        meetingTypeId: loadedTypes[0]?.id ?? "",
        durationMinutes: loadedTypes[0]?.allowed_durations_minutes[0] ?? 60,
      }));
    } catch (error) {
      setAuth({
        status: "error",
        message: error instanceof Error ? error.message : "Не удалось открыть Mini App",
      });
    }
  }

  async function refreshBookings() {
    if (isPreview) {
      return;
    }
    setBookings(await loadBookings());
  }

  async function refreshAvailableDates() {
    if (isPreview) {
      setAvailableDates(previewDates());
      return;
    }
    try {
      setAvailableDates(await loadAvailableDates());
    } catch (error) {
      showToast("error", errorText(error));
    }
  }

  async function refreshSlots() {
    if (isPreview) {
      setSlots(previewSlots(form.date));
      return;
    }
    try {
      setSlots(
        await loadSlots({
          date: form.date,
          meetingTypeId: form.meetingTypeId,
          durationMinutes: form.durationMinutes,
        }),
      );
    } catch (error) {
      setSlots([]);
      showToast("error", errorText(error));
    }
  }

  async function handleConsent(): Promise<boolean> {
    if (!user) {
      return false;
    }
    setIsBusy(true);
    try {
      if (!isPreview) {
        await acceptConsent();
        const profile = await loadProfile();
        setAuth((current) => (current.status === "ready" ? { ...current, user: profile } : current));
      } else {
        setAuth((current) =>
          current.status === "preview"
            ? { ...current, user: { ...current.user, has_consent: true } }
            : current,
        );
      }
      showToast("success", "Согласие принято");
      return true;
    } catch (error) {
      showToast("error", errorText(error));
      return false;
    } finally {
      setIsBusy(false);
    }
  }

  async function handleProceedFromDetails() {
    if (!personalDataConsentChecked) {
      showToast("error", "Нужно дать согласие на обработку персональных данных");
      return;
    }
    if (!user?.has_consent) {
      const accepted = await handleConsent();
      if (!accepted) {
        return;
      }
    }
    setFormStep("slot");
  }

  async function submitBooking() {
    const slot = selectedSlot(form.slotKey, slots);
    if (!slot || !form.meetingTypeId) {
      showToast("error", "Выберите дату и время");
      return;
    }
    setIsBusy(true);
    try {
      const payload: BookingCreatePayload = {
        full_name: form.fullName.trim(),
        email: form.email.trim(),
        meeting_type_id: form.meetingTypeId,
        duration_minutes: form.durationMinutes,
        starts_at: slot.starts_at,
        ends_at: slot.ends_at,
        user_comment: form.comment.trim() || null,
        previous_booking_id: form.previousBookingId,
      };
      const booking = isPreview ? previewCreatedBooking(payload) : await createBooking(payload);
      setBookings((current) => [booking, ...current.filter((item) => item.id !== booking.id)]);
      setForm({
        ...emptyForm,
        fullName: form.fullName,
        email: form.email,
        meetingTypeId: meetingTypes[0]?.id ?? "",
        durationMinutes: meetingTypes[0]?.allowed_durations_minutes[0] ?? 60,
      });
      setSlots([]);
      setFormStep("details");
      setActiveTab("calendar");
      showToast("success", form.previousBookingId ? "Запрос переноса отправлен" : "Заявка создана");
      if (!isPreview) {
        await refreshBookings();
      }
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleUserCancelBooking(booking: MiniAppBooking) {
    if (!canCancelBooking(booking)) {
      showToast("error", "Отмена недоступна менее чем за 2 часа до встречи");
      return;
    }
    setIsBusy(true);
    try {
      const updated = isPreview
        ? { ...booking, status: "cancelled_by_user", cancellation_reason: null }
        : await cancelBooking(booking.id, null);
      setBookings((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      showToast("success", "Заявка отменена");
      if (!isPreview) {
        await refreshBookings();
      }
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function refreshAdminData() {
    if (!user?.is_admin) {
      return;
    }
    if (isPreview) {
      setAdminDashboard(previewAdminDashboard());
      setAdminBookings(previewAdminCards(adminStatusFilter || undefined));
      setScheduleSettings(previewScheduleSettings());
      setWorkingHours(previewWorkingHours());
      setRestrictions(previewRestrictions());
      setAdminMeetingTypes(previewAdminMeetingTypes());
      setGoogleOAuthStatus({ connected: false, needs_reconnect: true, error_code: "preview" });
      return;
    }
    try {
      const today = new Date().toISOString().slice(0, 10);
      const [
        dashboard,
        cards,
        settings,
        hours,
        currentRestrictions,
        types,
        oauthStatus,
      ] = await Promise.all([
        loadAdminDashboard(),
        loadAdminBookings(adminStatusFilter || undefined),
        loadScheduleSettings(),
        loadWorkingHours(),
        loadScheduleRestrictions(today),
        loadAdminMeetingTypes(),
        loadGoogleOAuthStatus().catch(() => ({
          connected: false,
          needs_reconnect: true,
          error_code: "google_oauth_status_unavailable",
        })),
      ]);
      setAdminDashboard(dashboard);
      setAdminBookings(cards);
      setScheduleSettings(settings);
      setWorkingHours(hours);
      setRestrictions(currentRestrictions);
      setAdminMeetingTypes(types);
      setGoogleOAuthStatus(oauthStatus);
    } catch (error) {
      showToast("error", errorText(error));
    }
  }

  async function handleGoogleOAuthClick() {
    if (googleOAuthStatus?.connected && !googleOAuthStatus.needs_reconnect) {
      showToast("success", "Google Calendar подключен");
      return;
    }
    setIsBusy(true);
    try {
      const authorizationUrl = await startGoogleOAuth();
      const app = telegramApp();
      if (app?.openLink) {
        app.openLink(authorizationUrl);
      } else {
        window.location.href = authorizationUrl;
      }
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAdminConfirm(card: MiniAppAdminBookingCard) {
    setIsBusy(true);
    try {
      const updated = isPreview
        ? {
            ...card,
            booking: {
              ...card.booking,
              status: "confirmed",
              meeting_url: adminMeetingUrl || "https://meet.google.com/",
            },
          }
        : await confirmAdminBooking(card.booking.id, adminMeetingUrl.trim() || null);
      setSelectedAdminCard(updated);
      setAdminBookings((current) =>
        current.map((item) => (item.booking.id === updated.booking.id ? updated : item)),
      );
      setAdminMeetingUrl("");
      showToast("success", "Заявка подтверждена");
      if (!isPreview) {
        await refreshAdminData();
      }
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAdminReject(card: MiniAppAdminBookingCard) {
    setIsBusy(true);
    try {
      const updated = isPreview
        ? { ...card, booking: { ...card.booking, status: "rejected", rejection_reason: adminRejectReason || null } }
        : await rejectAdminBooking(card.booking.id, adminRejectReason.trim() || null);
      setSelectedAdminCard(updated);
      setAdminBookings((current) =>
        current.map((item) => (item.booking.id === updated.booking.id ? updated : item)),
      );
      setAdminRejectReason("");
      showToast("success", "Заявка отклонена");
      if (!isPreview) {
        await refreshAdminData();
      }
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAdminCancel(card: MiniAppAdminBookingCard) {
    if (!canCancelBooking(card.booking)) {
      showToast("error", "Отмена недоступна менее чем за 2 часа до встречи");
      return;
    }
    setIsBusy(true);
    try {
      const updated = isPreview
        ? {
            ...card,
            booking: { ...card.booking, status: "cancelled_by_user", cancellation_reason: null },
          }
        : await cancelAdminBooking(card.booking.id, null);
      setSelectedAdminCard(updated);
      setAdminBookings((current) =>
        current.map((item) => (item.booking.id === updated.booking.id ? updated : item)),
      );
      showToast("success", "Встреча отменена");
      if (!isPreview) {
        await refreshAdminData();
      }
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAddClosedDay() {
    if (!newClosedDay) {
      showToast("error", "Выберите дату ограничения");
      return;
    }
    setIsBusy(true);
    try {
      if (isPreview) {
        setRestrictions((current) => [
          {
            id: `preview-restriction-${Date.now()}`,
            restriction_date: newClosedDay,
            restriction_type: "closed_day",
            start_time: null,
            end_time: null,
            admin_comment: newClosedDayComment || null,
          },
          ...current,
        ]);
      } else {
        await addClosedDayRestriction(newClosedDay, newClosedDayComment.trim() || null);
        setRestrictions(await loadScheduleRestrictions(new Date().toISOString().slice(0, 10)));
      }
      setNewClosedDay("");
      setNewClosedDayComment("");
      showToast("success", "Ограничение добавлено");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAddClosedHours() {
    if (!newClosedHoursDate || !newClosedHoursStart || !newClosedHoursEnd) {
      showToast("error", "Укажите дату, начало и конец закрытых часов");
      return;
    }
    if (newClosedHoursStart >= newClosedHoursEnd) {
      showToast("error", "Начало закрытых часов должно быть раньше конца");
      return;
    }
    setIsBusy(true);
    try {
      if (isPreview) {
        setRestrictions((current) => [
          {
            id: `preview-restriction-${Date.now()}`,
            restriction_date: newClosedHoursDate,
            restriction_type: "time_interval",
            start_time: newClosedHoursStart,
            end_time: newClosedHoursEnd,
            admin_comment: newClosedHoursComment || null,
          },
          ...current,
        ]);
      } else {
        await addTimeIntervalRestriction({
          restrictionDate: newClosedHoursDate,
          startTime: newClosedHoursStart,
          endTime: newClosedHoursEnd,
          adminComment: newClosedHoursComment.trim() || null,
        });
        setRestrictions(await loadScheduleRestrictions(new Date().toISOString().slice(0, 10)));
      }
      setNewClosedHoursDate("");
      setNewClosedHoursStart("");
      setNewClosedHoursEnd("");
      setNewClosedHoursComment("");
      showToast("success", "Закрытые часы добавлены");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDeleteRestriction(restrictionId: string) {
    setIsBusy(true);
    try {
      if (!isPreview) {
        await deleteScheduleRestriction(restrictionId);
      }
      setRestrictions((current) => current.filter((item) => item.id !== restrictionId));
      showToast("success", "Ограничение удалено");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleUpdateScheduleSettings(payload: MiniAppScheduleSettingsUpdate) {
    setIsBusy(true);
    try {
      const updated = isPreview
        ? {
            ...(scheduleSettings ?? previewScheduleSettings()),
            ...payload,
          }
        : await updateScheduleSettings(payload);
      setScheduleSettings(updated);
      showToast("success", "Настройки расписания обновлены");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleUpdateWorkingHours(
    weekday: number,
    payload: MiniAppWorkingHoursUpdate,
  ) {
    setIsBusy(true);
    try {
      const updated = isPreview
        ? { weekday, ...payload }
        : await updateWorkingHours(weekday, payload);
      setWorkingHours((current) =>
        [...current.filter((item) => item.weekday !== weekday), updated].sort(
          (left, right) => left.weekday - right.weekday,
        ),
      );
      showToast("success", "Рабочие часы обновлены");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAddMeetingType() {
    const durations = newMeetingTypeDurations
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item) && item > 0);
    if (!newMeetingTypeName.trim() || !durations.length) {
      showToast("error", "Укажите название и длительности");
      return;
    }
    setIsBusy(true);
    try {
      const created = isPreview
        ? {
            id: `preview-type-${Date.now()}`,
            name: newMeetingTypeName.trim(),
            allowed_durations_minutes: durations,
            is_fixed_duration: durations.length === 1,
            is_active: true,
          }
        : await addAdminMeetingType({
            name: newMeetingTypeName.trim(),
            allowed_durations_minutes: durations,
            is_fixed_duration: durations.length === 1,
          });
      setAdminMeetingTypes((current) => [created, ...current]);
      setNewMeetingTypeName("");
      setNewMeetingTypeDurations("60");
      showToast("success", "Тип встречи добавлен");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleToggleMeetingType(type: MiniAppAdminMeetingType) {
    setIsBusy(true);
    try {
      if (!isPreview) {
        await setAdminMeetingTypeActive(type.id, !type.is_active);
      }
      setAdminMeetingTypes((current) =>
        current.map((item) =>
          item.id === type.id ? { ...item, is_active: !item.is_active } : item,
        ),
      );
      showToast("success", type.is_active ? "Тип отключен" : "Тип включен");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  function showToast(tone: ToastTone, text: string) {
    setToast({ tone, text });
    window.setTimeout(() => setToast(null), 3600);
  }

  const visibleTabs = useMemo(
    () => tabs.filter((tab) => !tab.adminOnly || user?.is_admin),
    [user?.is_admin],
  );

  if (auth.status === "loading") {
    return <LoadingScreen />;
  }
  if (auth.status === "error") {
    return <ErrorScreen message={auth.message} onRetry={() => void bootstrap()} />;
  }
  if (!user) {
    return <LoadingScreen />;
  }

  return (
    <main className="app-shell">
      <Header isPreview={isPreview} />

      <section className="content-panel">
        {activeTab === "home" ? (
          <BookingForm
            form={form}
            formStep={formStep}
            isBusy={isBusy}
            meetingTypes={meetingTypes}
            availableDates={availableSlotDates}
            slots={slots}
            activeBookingsCount={activeBookings(bookings)}
            consentChecked={personalDataConsentChecked}
            consentUrl={config?.consent_url}
            policyUrl={config?.policy_url}
            onConsentCheckedChange={setPersonalDataConsentChecked}
            onChange={setForm}
            onStepChange={setFormStep}
            onProceedFromDetails={() => void handleProceedFromDetails()}
            onSubmit={() => void submitBooking()}
          />
        ) : null}
        {activeTab === "calendar" ? (
          <CalendarScreen
            bookings={bookings}
            meetingTypes={meetingTypes}
            isBusy={isBusy}
            onCancel={(booking) => void handleUserCancelBooking(booking)}
          />
        ) : null}
        {activeTab === "admin" ? (
          <AdminScreen
            view={adminView}
            dashboard={adminDashboard}
            cards={adminBookings}
            selectedCard={selectedAdminCard}
            statusFilter={adminStatusFilter}
            meetingUrl={adminMeetingUrl}
            rejectReason={adminRejectReason}
            scheduleSettings={scheduleSettings}
            workingHours={workingHours}
            restrictions={restrictions}
            newClosedDay={newClosedDay}
            newClosedDayComment={newClosedDayComment}
            newClosedHoursDate={newClosedHoursDate}
            newClosedHoursStart={newClosedHoursStart}
            newClosedHoursEnd={newClosedHoursEnd}
            newClosedHoursComment={newClosedHoursComment}
            meetingTypes={adminMeetingTypes}
            googleOAuthStatus={googleOAuthStatus}
            newMeetingTypeName={newMeetingTypeName}
            newMeetingTypeDurations={newMeetingTypeDurations}
            isBusy={isBusy}
            onViewChange={setAdminView}
            onStatusFilterChange={setAdminStatusFilter}
            onSelectCard={setSelectedAdminCard}
            onMeetingUrlChange={setAdminMeetingUrl}
            onRejectReasonChange={setAdminRejectReason}
            onConfirm={(card) => void handleAdminConfirm(card)}
            onReject={(card) => void handleAdminReject(card)}
            onCancel={(card) => void handleAdminCancel(card)}
            onNewClosedDayChange={setNewClosedDay}
            onNewClosedDayCommentChange={setNewClosedDayComment}
            onAddClosedDay={() => void handleAddClosedDay()}
            onNewClosedHoursDateChange={setNewClosedHoursDate}
            onNewClosedHoursStartChange={setNewClosedHoursStart}
            onNewClosedHoursEndChange={setNewClosedHoursEnd}
            onNewClosedHoursCommentChange={setNewClosedHoursComment}
            onAddClosedHours={() => void handleAddClosedHours()}
            onDeleteRestriction={(id) => void handleDeleteRestriction(id)}
            onUpdateScheduleSettings={(payload) => void handleUpdateScheduleSettings(payload)}
            onUpdateWorkingHours={(weekday, payload) => void handleUpdateWorkingHours(weekday, payload)}
            onNewMeetingTypeNameChange={setNewMeetingTypeName}
            onNewMeetingTypeDurationsChange={setNewMeetingTypeDurations}
            onAddMeetingType={() => void handleAddMeetingType()}
            onToggleMeetingType={(type) => void handleToggleMeetingType(type)}
            onGoogleOAuthClick={() => void handleGoogleOAuthClick()}
          />
        ) : null}
      </section>

      {toast ? <ToastMessage toast={toast} /> : null}
      <BottomNav tabs={visibleTabs} activeTab={activeTab} onChange={setActiveTab} />
    </main>
  );
}

function Header({ isPreview }: { isPreview: boolean }) {
  return (
    <>
      <section className="top-panel">
        <div>
          <h1>Добрый день!</h1>
          <p>В данном приложении Вы можете записаться на встречу по финансам с Ириной Бирюковой.</p>
        </div>
      </section>
      {isPreview ? (
        <div className="notice">
          Предпросмотр вне Telegram. Авторизация, профиль и админ-доступ подключатся при открытии
          через Mini App.
        </div>
      ) : null}
    </>
  );
}

function BookingForm({
  form,
  formStep,
  isBusy,
  meetingTypes,
  availableDates,
  slots,
  activeBookingsCount,
  consentChecked,
  consentUrl,
  policyUrl,
  onConsentCheckedChange,
  onChange,
  onStepChange,
  onProceedFromDetails,
  onSubmit,
}: {
  form: BookingFormState;
  formStep: FormStep;
  isBusy: boolean;
  meetingTypes: MiniAppMeetingType[];
  availableDates: string[];
  slots: MiniAppSlot[];
  activeBookingsCount: number;
  consentChecked: boolean;
  consentUrl: string | null | undefined;
  policyUrl: string | null | undefined;
  onConsentCheckedChange: (checked: boolean) => void;
  onChange: (next: BookingFormState) => void;
  onStepChange: (step: FormStep) => void;
  onProceedFromDetails: () => void;
  onSubmit: () => void;
}) {
  const selectedMeetingType = meetingTypes.find((item) => item.id === form.meetingTypeId);
  const selected = selectedSlot(form.slotKey, slots);
  const [dateView, setDateView] = useState<DateViewMode>("month");
  const activeLimitReached = activeBookingsCount >= MAX_ACTIVE_BOOKINGS && !form.previousBookingId;
  const visibleDates = useMemo(
    () => datesForView(availableDates, form.date),
    [availableDates, form.date],
  );
  const periodLabel = datePeriodLabel(availableDates, form.date);
  const canMoveDatesBack = canMoveDateWindow(availableDates, form.date, -1);
  const canMoveDatesForward = canMoveDateWindow(availableDates, form.date, 1);

  function moveDateWindow(direction: -1 | 1) {
    const nextDate = nextDateForView(availableDates, form.date, direction);
    if (nextDate) {
      onChange({ ...form, date: nextDate, slotKey: "" });
      setDateView("month");
    }
  }

  return (
    <>
      <PanelHeader title={form.previousBookingId ? "Перенос встречи" : "Новая встреча"} action="3 шага" />
      <div className="stepper" aria-label="Шаги записи">
        {(["details", "slot", "review"] as FormStep[]).map((step, index) => (
          <span
            key={step}
            className={formStep === step ? "step step-active" : "step"}
          >
            {index + 1}
          </span>
        ))}
      </div>

      {formStep === "details" ? (
        <div className="form-grid">
          <label>
            <span>Имя</span>
            <input
              value={form.fullName}
              onChange={(event) => onChange({ ...form, fullName: event.target.value })}
              placeholder="Ваше имя"
            />
          </label>
          <label>
            <span>Email</span>
            <input
              value={form.email}
              type="email"
              onChange={(event) => onChange({ ...form, email: event.target.value })}
              placeholder="name@example.com"
            />
          </label>
          <label>
            <span>Тип встречи</span>
            <select
              value={form.meetingTypeId}
              onChange={(event) => {
                const nextType = meetingTypes.find((item) => item.id === event.target.value);
                onChange({
                  ...form,
                  meetingTypeId: event.target.value,
                  durationMinutes: nextType?.allowed_durations_minutes[0] ?? form.durationMinutes,
                  date: "",
                  slotKey: "",
                });
              }}
            >
              {meetingTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Длительность</span>
            <select
              value={form.durationMinutes}
              onChange={(event) =>
                onChange({
                  ...form,
                  durationMinutes: Number(event.target.value),
                  date: "",
                  slotKey: "",
                })
              }
            >
              {(selectedMeetingType?.allowed_durations_minutes ?? [60]).map((duration) => (
                <option key={duration} value={duration}>
                  {duration} минут
                </option>
              ))}
            </select>
          </label>
          <label className="wide-field">
            <span>Комментарий</span>
            <textarea
              value={form.comment}
              onChange={(event) => onChange({ ...form, comment: event.target.value })}
              placeholder="Что важно обсудить"
            />
          </label>
          <label className="consent-checkbox">
            <input
              type="checkbox"
              checked={consentChecked}
              onChange={(event) => onConsentCheckedChange(event.target.checked)}
            />
            <span>
              Даю согласие на обработку персональных данных для связи со мной и разбора заявки,
              принимаю{" "}
              <a href={policyUrl ?? "#"} target="_blank" rel="noreferrer">
                политику конфиденциальности
              </a>
              {consentUrl ? (
                <>
                  {" "}и{" "}
                  <a href={consentUrl} target="_blank" rel="noreferrer">
                    согласие на обработку
                  </a>
                </>
              ) : null}
              .
            </span>
          </label>
          <button
            type="button"
            className="primary-button"
            onClick={onProceedFromDetails}
            disabled={!form.fullName || !form.email || !form.meetingTypeId || !consentChecked || isBusy}
          >
            Выбрать дату и время
          </button>
        </div>
      ) : null}

      {formStep === "slot" ? (
        <>
          <div className="date-toolbar">
            <div className="date-view-switch" aria-label="Режим выбора даты">
              {(["month", "time"] as DateViewMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={dateView === mode ? "date-view-button date-view-button-active" : "date-view-button"}
                  onClick={() => setDateView(mode)}
                >
                  {dateViewLabel(mode)}
                </button>
              ))}
            </div>
            <div className="date-window-actions">
              <button
                type="button"
                className="icon-button"
                disabled={!canMoveDatesBack}
                onClick={() => moveDateWindow(-1)}
                aria-label="Предыдущий период"
              >
                <ChevronLeft size={18} aria-hidden="true" />
              </button>
              <button
                type="button"
                className="icon-button"
                disabled={!canMoveDatesForward}
                onClick={() => moveDateWindow(1)}
                aria-label="Следующий период"
              >
                <ChevronRight size={18} aria-hidden="true" />
              </button>
            </div>
          </div>
          {dateView === "month" ? (
            <>
              {periodLabel ? <p className="date-period-label">{periodLabel}</p> : null}
              <div className="date-strip date-strip-month">
                {visibleDates.map((date) => (
                  <button
                    key={date}
                    type="button"
                    className={form.date === date ? "date-pill date-pill-active" : "date-pill"}
                    onClick={() => {
                      onChange({ ...form, date, slotKey: "" });
                      setDateView("time");
                    }}
                  >
                    <span>{weekdayLabel(date)}</span>
                    <strong>{dayLabel(date)}</strong>
                  </button>
                ))}
              </div>
              {!availableDates.length ? (
                <p className="panel-copy">Нет доступных дат для выбранного типа встречи.</p>
              ) : null}
            </>
          ) : null}
          {dateView === "time" ? (
            <>
              {form.date ? <p className="date-period-label">{fullDateLabel(form.date)}</p> : null}
              <div className="slot-grid">
                {slots.map((slot) => {
                  const key = slotKey(slot);
                  return (
                    <button
                      key={key}
                      type="button"
                      className={form.slotKey === key ? "slot-button slot-button-active" : "slot-button"}
                      onClick={() => onChange({ ...form, slotKey: key })}
                    >
                      <Clock3 size={16} aria-hidden="true" />
                      {slot.label}
                    </button>
                  );
                })}
              </div>
              {!form.date ? <p className="panel-copy">Сначала выберите день в месяце.</p> : null}
              {form.date && !slots.length ? (
                <p className="panel-copy">На выбранную дату нет свободного времени.</p>
              ) : null}
            </>
          ) : null}
          <div className="action-row form-action-row">
            <button type="button" className="secondary-button" onClick={() => onStepChange("details")}>
              Назад
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={!form.slotKey || isBusy || activeLimitReached}
              onClick={() => onStepChange("review")}
            >
              Проверить заявку
            </button>
          </div>
          {activeLimitReached ? (
            <p className="panel-copy">Сейчас можно иметь не больше {MAX_ACTIVE_BOOKINGS} активных заявок.</p>
          ) : null}
        </>
      ) : null}

      {formStep === "review" ? (
        <div className="review-card">
          <ReviewRow label="Имя" value={form.fullName} />
          <ReviewRow label="Email" value={form.email} />
          <ReviewRow label="Тип" value={selectedMeetingType?.name ?? "Не выбран"} />
          <ReviewRow label="Время" value={selected ? dateTimeLabel(selected.starts_at) : "Не выбрано"} />
          <ReviewRow label="Комментарий" value={form.comment || "Без комментария"} />
          <div className="action-row form-action-row">
            <button type="button" className="secondary-button" onClick={() => onStepChange("slot")}>
              Назад
            </button>
            <button type="button" className="primary-button" disabled={isBusy} onClick={onSubmit}>
              {isBusy ? "Отправляем..." : form.previousBookingId ? "Отправить перенос" : "Отправить заявку"}
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}

function CalendarScreen({
  bookings,
  meetingTypes,
  isBusy,
  onCancel,
}: {
  bookings: MiniAppBooking[];
  meetingTypes: MiniAppMeetingType[];
  isBusy: boolean;
  onCancel: (booking: MiniAppBooking) => void;
}) {
  const [selectedBookingId, setSelectedBookingId] = useState<string | null>(null);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const sortedBookings = (bookings.length ? bookings : previewBookings()).slice().sort((left, right) => {
    const leftValue = left.created_at ?? left.starts_at;
    const rightValue = right.created_at ?? right.starts_at;
    return rightValue.localeCompare(leftValue);
  });
  const currentBookings = sortedBookings.filter((booking) => !isArchivedBooking(booking));
  const archivedBookings = sortedBookings.filter(isArchivedBooking);

  function renderBooking(booking: MiniAppBooking) {
    const isConfirmed = booking.status === "confirmed";
    const isCancellable = canCancelBooking(booking);
    const isExpandable = isConfirmed || isCancellable;
    const isSelected = selectedBookingId === booking.id;
    return (
      <Fragment key={booking.id}>
        <div className={isExpandable ? "booking-row booking-row-expandable" : "booking-row"}>
          <BookingSummary booking={booking} meetingTypes={meetingTypes} />
          <div className="booking-row-actions">
            {isConfirmed && booking.meeting_url ? <MeetingLink href={booking.meeting_url} compact /> : null}
            {isExpandable ? (
              <button
                type="button"
                className="booking-row-action-button"
                onClick={() => setSelectedBookingId(isSelected ? null : booking.id)}
              >
                {isSelected ? "Скрыть" : "Открыть"}
              </button>
            ) : (
              <Clock3 size={18} aria-hidden="true" />
            )}
          </div>
        </div>
        {isSelected ? (
          <BookingDetail
            booking={booking}
            meetingTypes={meetingTypes}
            isBusy={isBusy}
            onCancel={onCancel}
          />
        ) : null}
      </Fragment>
    );
  }

  return (
    <>
      <PanelHeader title="Мои заявки" action={`${currentBookings.length}`} />
      <div className="timeline-list compact-list">
        {currentBookings.map(renderBooking)}
      </div>
      <section className="archive-panel">
        <button
          type="button"
          className="archive-toggle"
          onClick={() => setIsArchiveOpen((current) => !current)}
          aria-expanded={isArchiveOpen}
        >
          <span>Архив</span>
          <strong>{archivedBookings.length}</strong>
        </button>
        {isArchiveOpen ? (
          <div className="timeline-list archive-list">
            {archivedBookings.length ? (
              archivedBookings.map(renderBooking)
            ) : (
              <p className="panel-copy">В архиве пока нет заявок.</p>
            )}
          </div>
        ) : null}
      </section>
    </>
  );
}

function BookingDetail({
  booking,
  meetingTypes,
  isBusy,
  onCancel,
}: {
  booking: MiniAppBooking;
  meetingTypes: MiniAppMeetingType[];
  isBusy: boolean;
  onCancel: (booking: MiniAppBooking) => void;
}) {
  return (
    <div className="detail-panel booking-inline-detail">
      <PanelHeader
        title={`Заявка ${bookingNumberLabel(booking)}`}
        action={statusLabel(booking.status)}
      />
      <ReviewRow label="Тип" value={bookingTypeName(meetingTypes, booking)} />
      <ReviewRow label="Дата" value={dateLabel(booking.starts_at)} />
      <ReviewRow label="Время" value={timeLabel(booking.starts_at)} />
      <ReviewRow label="Длительность" value={`${booking.duration_minutes} минут`} />
      <ReviewRow label="Статус" value={statusLabel(booking.status)} />
      <ReviewRow label="Комментарий" value={booking.user_comment || "Без комментария"} />
      {booking.meeting_url ? <MeetingLink href={booking.meeting_url} /> : null}
      {canCancelBooking(booking) ? (
        <div className="action-row">
          <button
            type="button"
            className="danger-button"
            disabled={isBusy}
            onClick={() => onCancel(booking)}
          >
            <XCircle size={18} aria-hidden="true" />
            Отменить
          </button>
        </div>
      ) : null}
    </div>
  );
}

function BookingSummary({
  booking,
  meetingTypes,
}: {
  booking: MiniAppBooking;
  meetingTypes: MiniAppMeetingType[];
}) {
  return (
    <div>
      <strong>{bookingNumberLabel(booking)}</strong>
      <span>Тип: {bookingTypeName(meetingTypes, booking)}</span>
      <span>Дата: {dateLabel(booking.starts_at)}</span>
      <span>Время: {timeLabel(booking.starts_at)}</span>
      <span>Статус: {statusLabel(booking.status)}</span>
    </div>
  );
}

function AdminScreen({
  view,
  dashboard,
  cards,
  selectedCard,
  statusFilter,
  meetingUrl,
  rejectReason,
  scheduleSettings,
  workingHours,
  restrictions,
  newClosedDay,
  newClosedDayComment,
  newClosedHoursDate,
  newClosedHoursStart,
  newClosedHoursEnd,
  newClosedHoursComment,
  meetingTypes,
  googleOAuthStatus,
  newMeetingTypeName,
  newMeetingTypeDurations,
  isBusy,
  onViewChange,
  onStatusFilterChange,
  onSelectCard,
  onMeetingUrlChange,
  onRejectReasonChange,
  onConfirm,
  onReject,
  onCancel,
  onNewClosedDayChange,
  onNewClosedDayCommentChange,
  onAddClosedDay,
  onNewClosedHoursDateChange,
  onNewClosedHoursStartChange,
  onNewClosedHoursEndChange,
  onNewClosedHoursCommentChange,
  onAddClosedHours,
  onDeleteRestriction,
  onUpdateScheduleSettings,
  onUpdateWorkingHours,
  onNewMeetingTypeNameChange,
  onNewMeetingTypeDurationsChange,
  onAddMeetingType,
  onToggleMeetingType,
  onGoogleOAuthClick,
}: {
  view: AdminView;
  dashboard: MiniAppAdminDashboard | null;
  cards: MiniAppAdminBookingCard[];
  selectedCard: MiniAppAdminBookingCard | null;
  statusFilter: AdminStatusFilter;
  meetingUrl: string;
  rejectReason: string;
  scheduleSettings: MiniAppScheduleSettings | null;
  workingHours: MiniAppWorkingHours[];
  restrictions: MiniAppScheduleRestriction[];
  newClosedDay: string;
  newClosedDayComment: string;
  newClosedHoursDate: string;
  newClosedHoursStart: string;
  newClosedHoursEnd: string;
  newClosedHoursComment: string;
  meetingTypes: MiniAppAdminMeetingType[];
  googleOAuthStatus: MiniAppGoogleOAuthStatus | null;
  newMeetingTypeName: string;
  newMeetingTypeDurations: string;
  isBusy: boolean;
  onViewChange: (view: AdminView) => void;
  onStatusFilterChange: (status: AdminStatusFilter) => void;
  onSelectCard: (card: MiniAppAdminBookingCard | null) => void;
  onMeetingUrlChange: (value: string) => void;
  onRejectReasonChange: (value: string) => void;
  onConfirm: (card: MiniAppAdminBookingCard) => void;
  onReject: (card: MiniAppAdminBookingCard) => void;
  onCancel: (card: MiniAppAdminBookingCard) => void;
  onNewClosedDayChange: (value: string) => void;
  onNewClosedDayCommentChange: (value: string) => void;
  onAddClosedDay: () => void;
  onNewClosedHoursDateChange: (value: string) => void;
  onNewClosedHoursStartChange: (value: string) => void;
  onNewClosedHoursEndChange: (value: string) => void;
  onNewClosedHoursCommentChange: (value: string) => void;
  onAddClosedHours: () => void;
  onDeleteRestriction: (id: string) => void;
  onUpdateScheduleSettings: (payload: MiniAppScheduleSettingsUpdate) => void;
  onUpdateWorkingHours: (weekday: number, payload: MiniAppWorkingHoursUpdate) => void;
  onNewMeetingTypeNameChange: (value: string) => void;
  onNewMeetingTypeDurationsChange: (value: string) => void;
  onAddMeetingType: () => void;
  onToggleMeetingType: (type: MiniAppAdminMeetingType) => void;
  onGoogleOAuthClick: () => void;
}) {
  return (
    <>
      <PanelHeader
        title="Админ"
        action={
          <AdminHeaderActions
            googleOAuthStatus={googleOAuthStatus}
            isBusy={isBusy}
            onGoogleOAuthClick={onGoogleOAuthClick}
          />
        }
      />
      <div className="admin-tabs">
        {adminViews.map((item) => (
          <button
            key={item.id}
            type="button"
            className={view === item.id ? "admin-tab admin-tab-active" : "admin-tab"}
            onClick={() => onViewChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {view === "requests" ? (
        <AdminRequestsView
          dashboard={dashboard}
          cards={cards}
          selectedCard={selectedCard}
          statusFilter={statusFilter}
          meetingUrl={meetingUrl}
          rejectReason={rejectReason}
          isBusy={isBusy}
          onStatusFilterChange={onStatusFilterChange}
          onSelectCard={onSelectCard}
          onMeetingUrlChange={onMeetingUrlChange}
          onRejectReasonChange={onRejectReasonChange}
          onConfirm={onConfirm}
          onReject={onReject}
          onCancel={onCancel}
        />
      ) : null}
      {view === "schedule" ? (
        <AdminScheduleView
          settings={scheduleSettings}
          workingHours={workingHours}
          restrictions={restrictions}
          newClosedDay={newClosedDay}
          newClosedDayComment={newClosedDayComment}
          newClosedHoursDate={newClosedHoursDate}
          newClosedHoursStart={newClosedHoursStart}
          newClosedHoursEnd={newClosedHoursEnd}
          newClosedHoursComment={newClosedHoursComment}
          isBusy={isBusy}
          onNewClosedDayChange={onNewClosedDayChange}
          onNewClosedDayCommentChange={onNewClosedDayCommentChange}
          onAddClosedDay={onAddClosedDay}
          onNewClosedHoursDateChange={onNewClosedHoursDateChange}
          onNewClosedHoursStartChange={onNewClosedHoursStartChange}
          onNewClosedHoursEndChange={onNewClosedHoursEndChange}
          onNewClosedHoursCommentChange={onNewClosedHoursCommentChange}
          onAddClosedHours={onAddClosedHours}
          onDeleteRestriction={onDeleteRestriction}
          onUpdateScheduleSettings={onUpdateScheduleSettings}
          onUpdateWorkingHours={onUpdateWorkingHours}
        />
      ) : null}
      {view === "types" ? (
        <AdminMeetingTypesView
          meetingTypes={meetingTypes}
          newMeetingTypeName={newMeetingTypeName}
          newMeetingTypeDurations={newMeetingTypeDurations}
          isBusy={isBusy}
          onNewMeetingTypeNameChange={onNewMeetingTypeNameChange}
          onNewMeetingTypeDurationsChange={onNewMeetingTypeDurationsChange}
          onAddMeetingType={onAddMeetingType}
          onToggleMeetingType={onToggleMeetingType}
        />
      ) : null}
    </>
  );
}

const adminViews: { id: AdminView; label: string }[] = [
  { id: "requests", label: "Заявки" },
  { id: "schedule", label: "Расписание" },
  { id: "types", label: "Типы" },
];

function AdminHeaderActions({
  googleOAuthStatus,
  isBusy,
  onGoogleOAuthClick,
}: {
  googleOAuthStatus: MiniAppGoogleOAuthStatus | null;
  isBusy: boolean;
  onGoogleOAuthClick: () => void;
}) {
  const isConnected = Boolean(googleOAuthStatus?.connected && !googleOAuthStatus.needs_reconnect);
  return (
    <div className="admin-header-actions">
      <button
        type="button"
        className="panel-badge oauth-badge-button"
        onClick={onGoogleOAuthClick}
        disabled={isBusy}
        title={isConnected ? "Google Calendar подключен" : "Нужно подтвердить Google Calendar"}
      >
        OAuth
        <span
          className={
            isConnected ? "oauth-status oauth-status-connected" : "oauth-status oauth-status-error"
          }
          aria-hidden="true"
        >
          V
        </span>
      </button>
      <span className="panel-badge">Mini App</span>
    </div>
  );
}

function AdminRequestsView({
  dashboard,
  cards,
  selectedCard,
  statusFilter,
  meetingUrl,
  rejectReason,
  isBusy,
  onStatusFilterChange,
  onSelectCard,
  onMeetingUrlChange,
  onRejectReasonChange,
  onConfirm,
  onReject,
  onCancel,
}: {
  dashboard: MiniAppAdminDashboard | null;
  cards: MiniAppAdminBookingCard[];
  selectedCard: MiniAppAdminBookingCard | null;
  statusFilter: AdminStatusFilter;
  meetingUrl: string;
  rejectReason: string;
  isBusy: boolean;
  onStatusFilterChange: (status: AdminStatusFilter) => void;
  onSelectCard: (card: MiniAppAdminBookingCard | null) => void;
  onMeetingUrlChange: (value: string) => void;
  onRejectReasonChange: (value: string) => void;
  onConfirm: (card: MiniAppAdminBookingCard) => void;
  onReject: (card: MiniAppAdminBookingCard) => void;
  onCancel: (card: MiniAppAdminBookingCard) => void;
}) {
  const metrics = dashboard?.metrics;
  const sortedCards = cards.slice().sort((left, right) => {
    const leftValue = left.booking.created_at ?? left.booking.starts_at;
    const rightValue = right.booking.created_at ?? right.booking.starts_at;
    return rightValue.localeCompare(leftValue);
  });
  const currentCards = sortedCards.filter((card) => !isArchivedBooking(card.booking));
  const archivedCards = sortedCards.filter((card) => isArchivedBooking(card.booking));
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);

  useEffect(() => {
    if (!selectedCard) {
      return;
    }
    if (!cards.some((card) => card.booking.id === selectedCard.booking.id)) {
      onSelectCard(null);
    }
  }, [cards, onSelectCard, selectedCard]);

  function handleStatusFilterChange(nextStatus: AdminStatusFilter) {
    onSelectCard(null);
    setIsArchiveOpen(false);
    onStatusFilterChange(nextStatus);
  }

  function renderAdminCard(card: MiniAppAdminBookingCard) {
    const isSelected = selectedCard?.booking.id === card.booking.id;
    return (
      <Fragment key={card.booking.id}>
        <div className="booking-row booking-row-expandable">
          <AdminBookingSummary card={card} />
          <div className="booking-row-actions">
            <button
              type="button"
              className="booking-row-action-button"
              onClick={() => onSelectCard(isSelected ? null : card)}
            >
              {isSelected ? "Скрыть" : "Открыть"}
            </button>
          </div>
        </div>
        {isSelected ? (
          <AdminBookingDetail
            card={card}
            meetingUrl={meetingUrl}
            rejectReason={rejectReason}
            isBusy={isBusy}
            onMeetingUrlChange={onMeetingUrlChange}
            onRejectReasonChange={onRejectReasonChange}
            onConfirm={onConfirm}
            onReject={onReject}
            onCancel={onCancel}
          />
        ) : null}
      </Fragment>
    );
  }

  return (
    <>
      <div className="admin-summary-grid">
        <AdminTile label="Ожидают" value={String(metrics?.pending ?? 0)} compact />
        <AdminTile label="Подтверждены" value={String(metrics?.confirmed ?? 0)} compact />
        <AdminTile label="Переносы" value={String(metrics?.reschedule_requested ?? 0)} compact />
        <AdminTile label="Отменены" value={String(metrics?.cancelled ?? 0)} compact />
      </div>
      <select
        className="admin-filter"
        value={statusFilter}
        onChange={(event) => handleStatusFilterChange(event.target.value as AdminStatusFilter)}
      >
        <option value="">Все</option>
        <option value="pending">Ожидают</option>
        <option value="confirmed">Подтверждены</option>
        <option value="reschedule_requested">Переносы</option>
        <option value="cancelled_by_user">Отменены</option>
        <option value="rejected">Отклонены</option>
      </select>
      <div className="timeline-list">
        {currentCards.length ? (
          currentCards.map(renderAdminCard)
        ) : (
          <p className="panel-copy">В выбранном списке нет активных заявок.</p>
        )}
      </div>
      <section className="archive-panel">
        <button
          type="button"
          className="archive-toggle"
          onClick={() => setIsArchiveOpen((current) => !current)}
          aria-expanded={isArchiveOpen}
        >
          <span>Архив</span>
          <strong>{archivedCards.length}</strong>
        </button>
        {isArchiveOpen ? (
          <div className="timeline-list archive-list">
            {archivedCards.length ? (
              archivedCards.map(renderAdminCard)
            ) : (
              <p className="panel-copy">В архиве пока нет заявок.</p>
            )}
          </div>
        ) : null}
      </section>
    </>
  );
}

function AdminBookingSummary({ card }: { card: MiniAppAdminBookingCard }) {
  return (
    <div>
      <strong>{bookingNumberLabel(card.booking)}</strong>
      <span>Клиент: {card.user.full_name || card.user.telegram_username || "Пользователь"}</span>
      <span>Тип: {card.meeting_type.name}</span>
      <span>Дата: {dateLabel(card.booking.starts_at)}</span>
      <span>Время: {timeLabel(card.booking.starts_at)}</span>
      <span>Статус: {statusLabel(card.booking.status)}</span>
    </div>
  );
}

function AdminBookingDetail({
  card,
  meetingUrl,
  rejectReason,
  isBusy,
  onMeetingUrlChange,
  onRejectReasonChange,
  onConfirm,
  onReject,
  onCancel,
}: {
  card: MiniAppAdminBookingCard;
  meetingUrl: string;
  rejectReason: string;
  isBusy: boolean;
  onMeetingUrlChange: (value: string) => void;
  onRejectReasonChange: (value: string) => void;
  onConfirm: (card: MiniAppAdminBookingCard) => void;
  onReject: (card: MiniAppAdminBookingCard) => void;
  onCancel: (card: MiniAppAdminBookingCard) => void;
}) {
  return (
    <div className="detail-panel booking-inline-detail">
      <PanelHeader
        title={`Заявка ${bookingNumberLabel(card.booking)}`}
        action={statusLabel(card.booking.status)}
      />
      <ReviewRow label="Клиент" value={card.user.full_name || "Без имени"} />
      <ReviewRow label="Email" value={card.user.email || "Не указан"} />
      <ReviewRow label="Тип" value={card.meeting_type.name} />
      <ReviewRow label="Дата" value={dateLabel(card.booking.starts_at)} />
      <ReviewRow label="Время" value={timeLabel(card.booking.starts_at)} />
      <ReviewRow label="Длительность" value={`${card.booking.duration_minutes} минут`} />
      <ReviewRow label="Статус" value={statusLabel(card.booking.status)} />
      <ReviewRow label="Комментарий" value={card.booking.user_comment || "Без комментария"} />
      {card.booking.rejection_reason ? (
        <ReviewRow label="Причина отклонения" value={card.booking.rejection_reason} />
      ) : null}
      {card.booking.cancellation_reason ? (
        <ReviewRow label="Причина отмены" value={card.booking.cancellation_reason} />
      ) : null}
      {card.booking.status === "confirmed" && card.booking.meeting_url ? (
        <MeetingLink href={card.booking.meeting_url} />
      ) : null}
      {card.booking.status === "pending" ? (
        <>
          <label className="wide-field">
            <span>Ссылка на встречу</span>
            <input
              value={meetingUrl}
              onChange={(event) => onMeetingUrlChange(event.target.value)}
              placeholder="Можно оставить пустым, если задан DEFAULT_MEETING_URL"
            />
          </label>
          <label className="wide-field">
            <span>Причина отклонения</span>
            <textarea
              value={rejectReason}
              onChange={(event) => onRejectReasonChange(event.target.value)}
              placeholder="Можно оставить пустым"
            />
          </label>
          <div className="action-row">
            <button
              type="button"
              className="secondary-button"
              disabled={isBusy}
              onClick={() => onConfirm(card)}
            >
              <CheckCircle2 size={18} aria-hidden="true" />
              Подтвердить
            </button>
            <button
              type="button"
              className="danger-button"
              disabled={isBusy}
              onClick={() => onReject(card)}
            >
              <XCircle size={18} aria-hidden="true" />
              Отклонить
            </button>
          </div>
        </>
      ) : null}
      {card.booking.status === "confirmed" && canCancelBooking(card.booking) ? (
        <div className="action-row">
          <button
            type="button"
            className="danger-button"
            disabled={isBusy}
            onClick={() => onCancel(card)}
          >
            <XCircle size={18} aria-hidden="true" />
            Отменить
          </button>
        </div>
      ) : null}
    </div>
  );
}

function AdminScheduleView({
  settings,
  workingHours,
  restrictions,
  newClosedDay,
  newClosedDayComment,
  newClosedHoursDate,
  newClosedHoursStart,
  newClosedHoursEnd,
  newClosedHoursComment,
  isBusy,
  onNewClosedDayChange,
  onNewClosedDayCommentChange,
  onAddClosedDay,
  onNewClosedHoursDateChange,
  onNewClosedHoursStartChange,
  onNewClosedHoursEndChange,
  onNewClosedHoursCommentChange,
  onAddClosedHours,
  onDeleteRestriction,
  onUpdateScheduleSettings,
  onUpdateWorkingHours,
}: {
  settings: MiniAppScheduleSettings | null;
  workingHours: MiniAppWorkingHours[];
  restrictions: MiniAppScheduleRestriction[];
  newClosedDay: string;
  newClosedDayComment: string;
  newClosedHoursDate: string;
  newClosedHoursStart: string;
  newClosedHoursEnd: string;
  newClosedHoursComment: string;
  isBusy: boolean;
  onNewClosedDayChange: (value: string) => void;
  onNewClosedDayCommentChange: (value: string) => void;
  onAddClosedDay: () => void;
  onNewClosedHoursDateChange: (value: string) => void;
  onNewClosedHoursStartChange: (value: string) => void;
  onNewClosedHoursEndChange: (value: string) => void;
  onNewClosedHoursCommentChange: (value: string) => void;
  onAddClosedHours: () => void;
  onDeleteRestriction: (id: string) => void;
  onUpdateScheduleSettings: (payload: MiniAppScheduleSettingsUpdate) => void;
  onUpdateWorkingHours: (weekday: number, payload: MiniAppWorkingHoursUpdate) => void;
}) {
  const [editingSetting, setEditingSetting] = useState<AdminScheduleSettingKey | null>(null);
  const [settingDraft, setSettingDraft] = useState("");
  const [editingWeekday, setEditingWeekday] = useState<number | null>(null);
  const [workingHoursDraft, setWorkingHoursDraft] = useState({
    isWorkingDay: true,
    startTime: "10:00",
    endTime: "18:00",
  });
  const editableSettings = adminScheduleSettingOptions(settings);
  const activeSetting = editableSettings.find((item) => item.key === editingSetting) ?? null;

  function beginSettingEdit(key: AdminScheduleSettingKey) {
    const option = editableSettings.find((item) => item.key === key);
    if (!option) {
      return;
    }
    setEditingSetting(key);
    setSettingDraft(String(option.value));
  }

  function changeSettingDraft(delta: number) {
    if (!activeSetting) {
      return;
    }
    const currentValue = Number(settingDraft || activeSetting.value);
    const nextValue = clampNumber(
      currentValue + delta,
      activeSetting.min,
      activeSetting.max,
    );
    setSettingDraft(String(nextValue));
  }

  function saveSettingDraft() {
    if (!settings || !editingSetting || !activeSetting) {
      return;
    }
    const nextValue = clampNumber(
      Number(settingDraft),
      activeSetting.min,
      activeSetting.max,
    );
    onUpdateScheduleSettings({
      booking_horizon_days: settings.booking_horizon_days,
      slot_step_minutes: settings.slot_step_minutes,
      meeting_buffer_minutes: settings.meeting_buffer_minutes,
      [editingSetting]: nextValue,
    });
    setEditingSetting(null);
  }

  function beginWorkingHoursEdit(row: MiniAppWorkingHours) {
    setEditingWeekday(row.weekday);
    setWorkingHoursDraft({
      isWorkingDay: row.is_working_day,
      startTime: timeInputValue(row.start_time) || "10:00",
      endTime: timeInputValue(row.end_time) || "18:00",
    });
  }

  function saveWorkingHoursDraft() {
    if (editingWeekday === null) {
      return;
    }
    onUpdateWorkingHours(editingWeekday, {
      is_working_day: workingHoursDraft.isWorkingDay,
      start_time: workingHoursDraft.isWorkingDay ? workingHoursDraft.startTime : null,
      end_time: workingHoursDraft.isWorkingDay ? workingHoursDraft.endTime : null,
    });
    setEditingWeekday(null);
  }

  return (
    <>
      <div className="admin-grid admin-grid-compact">
        <AdminTile label="Часовой пояс" value={settings?.timezone ?? "Не задан"} compact />
        {editableSettings.map((item) => (
          <AdminTile
            key={item.key}
            label={item.label}
            value={`${item.value} ${item.unit}`}
            compact
            onClick={() => beginSettingEdit(item.key)}
          />
        ))}
      </div>
      {activeSetting ? (
        <div className="detail-panel">
          <PanelHeader title={activeSetting.label} action="Изменить" />
          <div className="setting-editor">
            <button
              type="button"
              className="icon-button"
              disabled={isBusy}
              onClick={() => changeSettingDraft(-activeSetting.step)}
              aria-label="Уменьшить"
            >
              -
            </button>
            <label>
              <span>{activeSetting.unit}</span>
              <input
                type="number"
                min={activeSetting.min}
                max={activeSetting.max}
                step={activeSetting.step}
                value={settingDraft}
                onChange={(event) => setSettingDraft(event.target.value)}
              />
            </label>
            <button
              type="button"
              className="icon-button"
              disabled={isBusy}
              onClick={() => changeSettingDraft(activeSetting.step)}
              aria-label="Увеличить"
            >
              +
            </button>
          </div>
          <div className="action-row">
            <button type="button" className="secondary-button" onClick={() => setEditingSetting(null)}>
              Отмена
            </button>
            <button type="button" className="primary-button compact-primary" disabled={isBusy} onClick={saveSettingDraft}>
              Сохранить
            </button>
          </div>
        </div>
      ) : null}
      <div className="detail-panel">
        <PanelHeader title="Рабочие часы" action={`${workingHours.length}`} />
        <div className="working-hours-grid">
          {workingHours.map((row) => (
            <button
              key={row.weekday}
              type="button"
              className="booking-row booking-row-button working-hour-card"
              onClick={() => beginWorkingHoursEdit(row)}
            >
              <div>
                <strong>{weekdayName(row.weekday)}</strong>
                <span>{workingHoursLabel(row)}</span>
              </div>
              <span>Изменить</span>
            </button>
          ))}
        </div>
        {editingWeekday !== null ? (
          <div className="working-hours-editor">
            <PanelHeader title={weekdayName(editingWeekday)} action="Рабочие часы" />
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={workingHoursDraft.isWorkingDay}
                onChange={(event) =>
                  setWorkingHoursDraft((current) => ({
                    ...current,
                    isWorkingDay: event.target.checked,
                  }))
                }
              />
              <span>Рабочий день</span>
            </label>
            {workingHoursDraft.isWorkingDay ? (
              <div className="time-edit-grid">
                <label>
                  <span>Начало</span>
                  <input
                    type="time"
                    value={workingHoursDraft.startTime}
                    onChange={(event) =>
                      setWorkingHoursDraft((current) => ({
                        ...current,
                        startTime: event.target.value,
                      }))
                    }
                  />
                </label>
                <label>
                  <span>Конец</span>
                  <input
                    type="time"
                    value={workingHoursDraft.endTime}
                    onChange={(event) =>
                      setWorkingHoursDraft((current) => ({
                        ...current,
                        endTime: event.target.value,
                      }))
                    }
                  />
                </label>
              </div>
            ) : null}
            <div className="action-row">
              <button type="button" className="secondary-button" onClick={() => setEditingWeekday(null)}>
                Отмена
              </button>
              <button
                type="button"
                className="primary-button compact-primary"
                disabled={isBusy}
                onClick={saveWorkingHoursDraft}
              >
                Сохранить
              </button>
            </div>
          </div>
        ) : null}
      </div>
      <div className="detail-panel">
        <PanelHeader title="Закрытый день" action="Добавить" />
        <div className="form-grid">
          <label>
            <span>Дата</span>
            <input
              type="date"
              value={newClosedDay}
              onChange={(event) => onNewClosedDayChange(event.target.value)}
            />
          </label>
          <label className="wide-field compact-textarea-field">
            <span>Комментарий</span>
            <textarea
              value={newClosedDayComment}
              onChange={(event) => onNewClosedDayCommentChange(event.target.value)}
              placeholder="Причина ограничения"
            />
          </label>
          <button
            type="button"
            className="primary-button"
            disabled={isBusy}
            onClick={onAddClosedDay}
          >
            Добавить ограничение
          </button>
        </div>
      </div>
      <div className="detail-panel">
        <PanelHeader title="Закрытые часы" action="Добавить" />
        <div className="form-grid">
          <label>
            <span>Дата</span>
            <input
              type="date"
              value={newClosedHoursDate}
              onChange={(event) => onNewClosedHoursDateChange(event.target.value)}
            />
          </label>
          <label>
            <span>Начало</span>
            <input
              type="time"
              value={newClosedHoursStart}
              onChange={(event) => onNewClosedHoursStartChange(event.target.value)}
            />
          </label>
          <label>
            <span>Конец</span>
            <input
              type="time"
              value={newClosedHoursEnd}
              onChange={(event) => onNewClosedHoursEndChange(event.target.value)}
            />
          </label>
          <label className="wide-field compact-textarea-field">
            <span>Комментарий</span>
            <textarea
              value={newClosedHoursComment}
              onChange={(event) => onNewClosedHoursCommentChange(event.target.value)}
              placeholder="Например: занято, личная встреча"
            />
          </label>
          <button
            type="button"
            className="primary-button"
            disabled={isBusy}
            onClick={onAddClosedHours}
          >
            Добавить закрытые часы
          </button>
        </div>
      </div>
      <div className="timeline-list">
        {restrictions.map((restriction) => (
          <div key={restriction.id} className="booking-row">
            <div>
              <strong>{dateLabel(restriction.restriction_date)}</strong>
              <span>{restrictionLabel(restriction)}</span>
            </div>
            <button
              type="button"
              className="danger-button compact-action"
              disabled={isBusy}
              onClick={() => onDeleteRestriction(restriction.id)}
            >
              Удалить
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

function AdminMeetingTypesView({
  meetingTypes,
  newMeetingTypeName,
  newMeetingTypeDurations,
  isBusy,
  onNewMeetingTypeNameChange,
  onNewMeetingTypeDurationsChange,
  onAddMeetingType,
  onToggleMeetingType,
}: {
  meetingTypes: MiniAppAdminMeetingType[];
  newMeetingTypeName: string;
  newMeetingTypeDurations: string;
  isBusy: boolean;
  onNewMeetingTypeNameChange: (value: string) => void;
  onNewMeetingTypeDurationsChange: (value: string) => void;
  onAddMeetingType: () => void;
  onToggleMeetingType: (type: MiniAppAdminMeetingType) => void;
}) {
  return (
    <>
      <div className="detail-panel">
        <PanelHeader title="Новый тип" action="MVP" />
        <div className="form-grid">
          <label>
            <span>Название</span>
            <input
              value={newMeetingTypeName}
              onChange={(event) => onNewMeetingTypeNameChange(event.target.value)}
              placeholder="Например: Разбор"
            />
          </label>
          <label>
            <span>Длительности через запятую</span>
            <input
              value={newMeetingTypeDurations}
              onChange={(event) => onNewMeetingTypeDurationsChange(event.target.value)}
              placeholder="30,60"
            />
          </label>
          <button
            type="button"
            className="primary-button"
            disabled={isBusy}
            onClick={onAddMeetingType}
          >
            Добавить тип встречи
          </button>
        </div>
      </div>
      <div className="timeline-list">
        {meetingTypes.map((type) => (
          <div key={type.id} className="booking-row">
            <div>
              <strong>{type.name}</strong>
              <span>{type.allowed_durations_minutes.join(", ")} минут</span>
            </div>
            <button
              type="button"
              className={type.is_active ? "secondary-button compact-action" : "danger-button compact-action"}
              disabled={isBusy}
              onClick={() => onToggleMeetingType(type)}
            >
              {type.is_active ? "Активен" : "Выключен"}
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

function LoadingScreen() {
  return (
    <main className="center-screen">
      <Loader2 className="spin" size={28} aria-hidden="true" />
      <span>Открываем Mini App</span>
    </main>
  );
}

function ErrorScreen({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className="center-screen">
      <div className="error-mark">!</div>
      <h1>Mini App недоступна</h1>
      <p>{message}</p>
      <button type="button" className="primary-button" onClick={onRetry}>
        Повторить
      </button>
    </main>
  );
}

function BottomNav({
  tabs,
  activeTab,
  onChange,
}: {
  tabs: Tab[];
  activeTab: TabId;
  onChange: (tab: TabId) => void;
}) {
  return (
    <nav className="bottom-nav" aria-label="Навигация Mini App">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            className={isActive ? "nav-item nav-item-active" : "nav-item"}
            onClick={() => onChange(tab.id)}
            aria-current={isActive ? "page" : undefined}
          >
            <Icon size={20} strokeWidth={2.2} aria-hidden="true" />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function PanelHeader({ title, action }: { title: string; action: ReactNode }) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      <div className="panel-header-action">
        {typeof action === "string" ? <span className="panel-badge">{action}</span> : action}
      </div>
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="review-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MeetingLink({ href, compact = false }: { href: string; compact?: boolean }) {
  return (
    <a
      className={compact ? "meeting-url-link meeting-url-link-compact" : "meeting-url-link"}
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      Ссылка на видеовстречу
    </a>
  );
}

function AdminTile({
  label,
  value,
  compact = false,
  onClick,
}: {
  label: string;
  value: string;
  compact?: boolean;
  onClick?: () => void;
}) {
  const className = compact ? "admin-tile admin-tile-compact" : "admin-tile";
  if (onClick) {
    return (
      <button type="button" className={`${className} admin-tile-button`} onClick={onClick}>
        <span>{label}</span>
        <strong>{value}</strong>
      </button>
    );
  }
  return (
    <div className={className}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ToastMessage({ toast }: { toast: NonNullable<Toast> }) {
  return (
    <div className={`toast toast-${toast.tone}`} role="status">
      {toast.tone === "success" ? <CheckCircle2 size={18} aria-hidden="true" /> : null}
      {toast.tone === "error" ? <XCircle size={18} aria-hidden="true" /> : null}
      {toast.tone === "info" ? <MessageSquare size={18} aria-hidden="true" /> : null}
      <span>{toast.text}</span>
    </div>
  );
}

function dateViewLabel(mode: DateViewMode): string {
  const labels: Record<DateViewMode, string> = {
    month: "Месяц",
    time: "Время",
  };
  return labels[mode];
}

function datesForView(dates: string[], selectedDate: string): string[] {
  if (!dates.length) {
    return [];
  }

  const anchorDate = dateViewAnchor(dates, selectedDate);
  if (!anchorDate) {
    return [];
  }

  const month = monthKey(anchorDate);
  return dates.filter((date) => monthKey(date) === month);
}

function datePeriodLabel(dates: string[], selectedDate: string): string {
  const anchorDate = dateViewAnchor(dates, selectedDate);
  if (!anchorDate) {
    return "";
  }

  return monthYearLabel(anchorDate);
}

function canMoveDateWindow(
  dates: string[],
  selectedDate: string,
  direction: -1 | 1,
): boolean {
  return Boolean(nextDateForView(dates, selectedDate, direction));
}

function nextDateForView(
  dates: string[],
  selectedDate: string,
  direction: -1 | 1,
): string | null {
  if (!dates.length) {
    return null;
  }

  const anchorDate = dateViewAnchor(dates, selectedDate);
  if (!anchorDate) {
    return null;
  }

  const currentMonth = monthKey(anchorDate);
  const candidates = direction > 0
    ? dates.filter((date) => monthKey(date) > currentMonth)
    : dates.filter((date) => monthKey(date) < currentMonth);
  return direction > 0 ? candidates[0] ?? null : candidates[candidates.length - 1] ?? null;
}

function dateViewAnchor(dates: string[], selectedDate: string): string | null {
  if (!dates.length) {
    return null;
  }

  if (selectedDate && dates.includes(selectedDate)) {
    return selectedDate;
  }

  return dates[0];
}

function monthKey(value: string): string {
  return value.slice(0, 7);
}

function monthYearLabel(value: string): string {
  return capitalizeFirst(
    new Intl.DateTimeFormat("ru-RU", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(utcDate(value)),
  );
}

function fullDateLabel(value: string): string {
  return capitalizeFirst(
    new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "long",
      year: "numeric",
      weekday: "long",
      timeZone: "UTC",
    }).format(utcDate(value)),
  );
}

function utcDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function capitalizeFirst(value: string): string {
  return value ? `${value[0].toUpperCase()}${value.slice(1)}` : value;
}

function selectedSlot(key: string, slots: MiniAppSlot[]): MiniAppSlot | null {
  return slots.find((slot) => slotKey(slot) === key) ?? null;
}

function slotKey(slot: MiniAppSlot): string {
  return `${slot.starts_at}|${slot.ends_at}`;
}

function activeBookings(bookings: MiniAppBooking[]): number {
  return bookings.filter((booking) =>
    ["pending", "confirmed", "reschedule_requested"].includes(booking.status),
  ).length;
}

function canCancelBooking(booking: MiniAppBooking): boolean {
  if (booking.status === "pending") {
    return true;
  }
  if (booking.status !== "confirmed") {
    return false;
  }
  return new Date(booking.starts_at).getTime() - Date.now() >= 2 * 60 * 60 * 1000;
}

function isArchivedBooking(booking: MiniAppBooking): boolean {
  if (["cancelled_by_user", "rejected"].includes(booking.status)) {
    return true;
  }
  return new Date(booking.starts_at).getTime() < Date.now();
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "Ожидает",
    confirmed: "Подтверждена",
    rejected: "Отклонена",
    cancelled_by_user: "Отменена",
    reschedule_requested: "Перенос",
    rescheduled: "Перенесена",
  };
  return labels[status] ?? status;
}

function bookingNumberLabel(booking: MiniAppBooking): string {
  return booking.display_number ? `№${booking.display_number}` : "№-";
}

function bookingTypeName(types: MiniAppMeetingType[], booking: MiniAppBooking): string {
  return (
    types.find((type) => type.id === booking.meeting_type_id)?.name ??
    previewMeetingTypes.find((type) => type.id === booking.meeting_type_id)?.name ??
    "Встреча"
  );
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
  }).format(new Date(value));
}

function timeLabel(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function restrictionLabel(restriction: MiniAppScheduleRestriction): string {
  const comment = restriction.admin_comment ? ` · ${restriction.admin_comment}` : "";
  if (restriction.restriction_type === "time_interval" && restriction.start_time && restriction.end_time) {
    return `${restriction.start_time.slice(0, 5)} - ${restriction.end_time.slice(0, 5)}${comment}`;
  }
  return `Весь день${comment}`;
}

function dateTimeLabel(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function weekdayLabel(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", { weekday: "short" }).format(new Date(value));
}

function dayLabel(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit" }).format(new Date(value));
}

function weekdayName(weekday: number): string {
  const labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  return labels[weekday] ?? String(weekday);
}

function adminScheduleSettingOptions(settings: MiniAppScheduleSettings | null): Array<{
  key: AdminScheduleSettingKey;
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  step: number;
}> {
  return [
    {
      key: "booking_horizon_days",
      label: "Горизонт",
      unit: "дней",
      value: settings?.booking_horizon_days ?? 0,
      min: 1,
      max: 365,
      step: 1,
    },
    {
      key: "slot_step_minutes",
      label: "Шаг слота",
      unit: "мин",
      value: settings?.slot_step_minutes ?? 0,
      min: 5,
      max: 240,
      step: 5,
    },
    {
      key: "meeting_buffer_minutes",
      label: "Буфер",
      unit: "мин",
      value: settings?.meeting_buffer_minutes ?? 0,
      min: 0,
      max: 240,
      step: 5,
    },
  ];
}

function workingHoursLabel(row: MiniAppWorkingHours): string {
  if (!row.is_working_day) {
    return "Выходной";
  }
  return `${timeInputValue(row.start_time)} - ${timeInputValue(row.end_time)}`;
}

function timeInputValue(value: string | null): string {
  return value ? value.slice(0, 5) : "";
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

function errorText(error: unknown): string {
  if (!(error instanceof Error)) {
    return "Не удалось выполнить действие";
  }

  const labels: Record<string, string> = {
    "User cannot have more active bookings.":
      "У вас уже есть максимум активных заявок. Отмените одну из текущих или дождитесь решения администратора.",
    max_active_bookings:
      "У вас уже есть максимум активных заявок. Отмените одну из текущих или дождитесь решения администратора.",
    "Blocked users cannot create bookings.": "Запись сейчас недоступна. Обратитесь к администратору.",
    user_blocked: "Запись сейчас недоступна. Обратитесь к администратору.",
    "Google Calendar is not connected.":
      "Google Calendar не подключен. Проверьте настройки календаря на сервере.",
    google_calendar_not_connected:
      "Google Calendar не подключен. Проверьте настройки календаря на сервере.",
    "Google Calendar access is lost.":
      "Доступ к Google Calendar потерян. Нужно заново подключить календарь.",
    google_calendar_access_lost:
      "Доступ к Google Calendar потерян. Нужно заново подключить календарь.",
    "Google Calendar failed: freebusy.":
      "Не удалось проверить занятость Google Calendar. Проверьте подключение календаря и попробуйте снова.",
    google_calendar_api_error:
      "Не удалось выполнить запрос к Google Calendar. Проверьте календарь и попробуйте снова.",
    "Selected slot is busy in Google Calendar.":
      "Этот слот уже занят в Google Calendar. Выберите другое время.",
    calendar_conflict: "Этот слот уже занят в Google Calendar. Выберите другое время.",
    cancellation_deadline_passed: "Отмена недоступна менее чем за 2 часа до встречи.",
    booking_not_cancellable: "Эту заявку нельзя отменить.",
  };

  return labels[error.message] ?? error.message;
}

function previewDates(): string[] {
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(Date.now() + (index + 1) * 86400000);
    return date.toISOString().slice(0, 10);
  });
}

function previewSlots(date: string): MiniAppSlot[] {
  if (!date) {
    return [];
  }
  return ["10:00", "11:30", "14:00", "16:30"].map((time) => {
    const startsAt = new Date(`${date}T${time}:00+03:00`);
    const endsAt = new Date(startsAt.getTime() + 60 * 60000);
    return {
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      label: time,
    };
  });
}

function previewCreatedBooking(payload: BookingCreatePayload): MiniAppBooking {
  return {
    id: `preview-${Date.now()}`,
    display_number: Math.floor(Date.now() / 1000),
    status: "pending",
    meeting_type_id: payload.meeting_type_id,
    duration_minutes: payload.duration_minutes,
    starts_at: payload.starts_at,
    ends_at: payload.ends_at,
    user_comment: payload.user_comment,
    rejection_reason: null,
    cancellation_reason: null,
    reserved_until: null,
    meeting_url: null,
    is_reschedule_request: Boolean(payload.previous_booking_id),
    previous_booking_id: payload.previous_booking_id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function previewBookings(): MiniAppBooking[] {
  const now = Date.now();
  return [
    {
      id: "preview-1",
      display_number: 1,
      status: "pending",
      meeting_type_id: "preview-consultation",
      duration_minutes: 60,
      starts_at: new Date(now + 86400000).toISOString(),
      ends_at: new Date(now + 90000000).toISOString(),
      user_comment: "Обсудить проект",
      rejection_reason: null,
      cancellation_reason: null,
      reserved_until: null,
      meeting_url: null,
      is_reschedule_request: false,
      previous_booking_id: null,
      created_at: null,
      updated_at: null,
    },
    {
      id: "preview-2",
      display_number: 2,
      status: "confirmed",
      meeting_type_id: "preview-diagnostics",
      duration_minutes: 60,
      starts_at: new Date(now + 172800000).toISOString(),
      ends_at: new Date(now + 176400000).toISOString(),
      user_comment: null,
      rejection_reason: null,
      cancellation_reason: null,
      reserved_until: null,
      meeting_url: "https://meet.google.com/",
      is_reschedule_request: false,
      previous_booking_id: null,
      created_at: null,
      updated_at: null,
    },
  ];
}

function previewAdminCards(status?: string): MiniAppAdminBookingCard[] {
  return previewBookings()
    .filter((booking) => !status || booking.status === status)
    .map((booking, index) => ({
      booking,
      user: {
        id: `preview-user-${index + 1}`,
        telegram_id: 550894 + index,
        telegram_username: index === 0 ? "client_project" : "client_meet",
        full_name: index === 0 ? "Анна Клиентова" : "Мария Петрова",
        email: index === 0 ? "anna@example.com" : "maria@example.com",
        has_consent: true,
        is_blocked: false,
        is_admin: false,
      },
      meeting_type: previewMeetingTypes[index] ?? previewMeetingTypes[0],
    }));
}

function previewAdminDashboard(): MiniAppAdminDashboard {
  const bookings = previewBookings();
  return {
    metrics: {
      pending: 1,
      confirmed: 1,
      reschedule_requested: 0,
      cancelled: 0,
    },
    upcoming: bookings,
    recent_pending: bookings.filter((booking) => booking.status === "pending"),
  };
}

function previewScheduleSettings(): MiniAppScheduleSettings {
  return {
    timezone: "Europe/Moscow",
    min_booking_lead_days: 1,
    booking_horizon_days: 21,
    slot_step_minutes: 30,
    meeting_buffer_minutes: 15,
  };
}

function previewWorkingHours(): MiniAppWorkingHours[] {
  return [
    { weekday: 0, is_working_day: true, start_time: "10:00", end_time: "18:00" },
    { weekday: 1, is_working_day: true, start_time: "10:00", end_time: "18:00" },
    { weekday: 2, is_working_day: true, start_time: "10:00", end_time: "18:00" },
    { weekday: 3, is_working_day: true, start_time: "10:00", end_time: "18:00" },
    { weekday: 4, is_working_day: true, start_time: "10:00", end_time: "16:00" },
    { weekday: 5, is_working_day: false, start_time: null, end_time: null },
    { weekday: 6, is_working_day: false, start_time: null, end_time: null },
  ];
}

function previewRestrictions(): MiniAppScheduleRestriction[] {
  const date = previewDates()[2];
  return [
    {
      id: "preview-restriction-1",
      restriction_date: date,
      restriction_type: "closed_day",
      start_time: null,
      end_time: null,
      admin_comment: "Личный день без встреч",
    },
  ];
}

function previewAdminMeetingTypes(): MiniAppAdminMeetingType[] {
  return previewMeetingTypes.map((type, index) => ({
    ...type,
    is_active: index === 0,
  }));
}
