import {
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  LayoutDashboard,
  Link as LinkIcon,
  Loader2,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UserRound,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  acceptConsent,
  addAdminMeetingType,
  addClosedDayRestriction,
  addTimeIntervalRestriction,
  cancelBooking,
  confirmAdminBooking,
  createBooking,
  deleteScheduleRestriction,
  loadAdminBookings,
  loadAdminCalendar,
  loadAdminDashboard,
  loadAdminMeetingTypes,
  loadAvailableDates,
  loadBookings,
  loadConfig,
  loadMeetingTypes,
  loadProfile,
  loadScheduleRestrictions,
  loadScheduleSettings,
  loadSlots,
  loadWorkingHours,
  miniAppAuth,
  prepareReschedule,
  rejectAdminBooking,
  setAdminMeetingTypeActive,
  trackMiniAppEvent,
} from "./api";
import { initTelegramShell, telegramApp } from "./telegram";
import type {
  AuthState,
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

type TabId = "home" | "bookings" | "calendar" | "admin" | "profile";
type FormStep = "details" | "slot" | "review";
type DateViewMode = "month" | "time";
type ToastTone = "success" | "error" | "info";
type Toast = { tone: ToastTone; text: string } | null;
type AdminStatusFilter = "" | "pending" | "confirmed" | "reschedule_requested" | "rejected";
type AdminView = "dashboard" | "requests" | "calendar" | "schedule" | "types";

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
  { id: "bookings", label: "Заявки", icon: FileText },
  { id: "calendar", label: "Календарь", icon: CalendarDays },
  { id: "admin", label: "Админ", icon: ShieldCheck, adminOnly: true },
  { id: "profile", label: "Профиль", icon: UserRound },
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
  const [slots, setSlots] = useState<MiniAppSlot[]>([]);
  const [form, setForm] = useState<BookingFormState>(emptyForm);
  const [formStep, setFormStep] = useState<FormStep>("details");
  const [selectedBooking, setSelectedBooking] = useState<MiniAppBooking | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [toast, setToast] = useState<Toast>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [adminView, setAdminView] = useState<AdminView>("dashboard");
  const [adminStatusFilter, setAdminStatusFilter] = useState<AdminStatusFilter>("pending");
  const [adminDashboard, setAdminDashboard] = useState<MiniAppAdminDashboard | null>(null);
  const [adminBookings, setAdminBookings] = useState<MiniAppAdminBookingCard[]>([]);
  const [adminCalendar, setAdminCalendar] = useState<MiniAppBooking[]>([]);
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
      return;
    }
    void refreshAvailableDates();
  }, [form.meetingTypeId, form.durationMinutes, auth.status]);

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
        setBookings(previewBookingsData);
        setMeetingTypes(previewMeetingTypes);
        setAvailableDates(previewDates());
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

  async function handleConsent() {
    if (!user) {
      return;
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
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
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
      setActiveTab("bookings");
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

  async function handleCancelBooking(booking: MiniAppBooking) {
    setIsBusy(true);
    try {
      const updated = isPreview
        ? { ...booking, status: "cancelled_by_user", cancellation_reason: cancelReason || null }
        : await cancelBooking(booking.id, cancelReason.trim() || null);
      setBookings((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedBooking(updated);
      setCancelReason("");
      showToast("success", "Заявка отменена");
    } catch (error) {
      showToast("error", errorText(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleReschedule(booking: MiniAppBooking) {
    setIsBusy(true);
    try {
      const prepared = isPreview ? booking : await prepareReschedule(booking.id);
      setForm((current) => ({
        ...current,
        previousBookingId: prepared.id,
        meetingTypeId: prepared.meeting_type_id,
        durationMinutes: prepared.duration_minutes,
        comment: "Запрос переноса встречи",
      }));
      setSelectedBooking(null);
      setFormStep("slot");
      setActiveTab("home");
      showToast("info", "Выберите новую дату и время");
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
      setAdminCalendar(previewBookings().filter((booking) => booking.status === "confirmed"));
      setScheduleSettings(previewScheduleSettings());
      setWorkingHours(previewWorkingHours());
      setRestrictions(previewRestrictions());
      setAdminMeetingTypes(previewAdminMeetingTypes());
      return;
    }
    try {
      const today = new Date().toISOString().slice(0, 10);
      const [
        dashboard,
        cards,
        calendar,
        settings,
        hours,
        currentRestrictions,
        types,
      ] = await Promise.all([
        loadAdminDashboard(),
        loadAdminBookings(adminStatusFilter || undefined),
        loadAdminCalendar(),
        loadScheduleSettings(),
        loadWorkingHours(),
        loadScheduleRestrictions(today),
        loadAdminMeetingTypes(),
      ]);
      setAdminDashboard(dashboard);
      setAdminBookings(cards);
      setAdminCalendar(calendar);
      setScheduleSettings(settings);
      setWorkingHours(hours);
      setRestrictions(currentRestrictions);
      setAdminMeetingTypes(types);
    } catch (error) {
      showToast("error", errorText(error));
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
      <Header user={user} bookings={bookings} isPreview={isPreview} />

      {!user.has_consent ? (
        <ConsentScreen
          consentUrl={config?.consent_url}
          policyUrl={config?.policy_url}
          isBusy={isBusy}
          onAccept={() => void handleConsent()}
        />
      ) : (
        <>
          <section className="metrics-grid" aria-label="Сводка">
            <MetricCard label="Активные" value={String(activeBookings(bookings))} tone="green" />
            <MetricCard label="Ожидают" value={String(pendingBookings(bookings))} tone="purple" />
            <MetricCard label="Ближайшая" value={nextBookingLabel(bookings)} tone="peach" />
          </section>

          <section className="content-panel">
            {activeTab === "home" ? (
              <BookingForm
                form={form}
                formStep={formStep}
                isBusy={isBusy}
                meetingTypes={meetingTypes}
                availableDates={availableDates}
                slots={slots}
                activeBookingsCount={activeBookings(bookings)}
                onChange={setForm}
                onStepChange={setFormStep}
                onSubmit={() => void submitBooking()}
              />
            ) : null}
            {activeTab === "bookings" ? (
              <BookingsScreen
                bookings={bookings}
                selectedBooking={selectedBooking}
                cancelReason={cancelReason}
                isBusy={isBusy}
                onSelect={setSelectedBooking}
                onCancelReasonChange={setCancelReason}
                onCancel={(booking) => void handleCancelBooking(booking)}
                onReschedule={(booking) => void handleReschedule(booking)}
              />
            ) : null}
            {activeTab === "calendar" ? <CalendarScreen bookings={bookings} /> : null}
            {activeTab === "admin" ? (
              <AdminScreen
                view={adminView}
                dashboard={adminDashboard}
                cards={adminBookings}
                calendar={adminCalendar}
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
                onNewClosedDayChange={setNewClosedDay}
                onNewClosedDayCommentChange={setNewClosedDayComment}
                onAddClosedDay={() => void handleAddClosedDay()}
                onNewClosedHoursDateChange={setNewClosedHoursDate}
                onNewClosedHoursStartChange={setNewClosedHoursStart}
                onNewClosedHoursEndChange={setNewClosedHoursEnd}
                onNewClosedHoursCommentChange={setNewClosedHoursComment}
                onAddClosedHours={() => void handleAddClosedHours()}
                onDeleteRestriction={(id) => void handleDeleteRestriction(id)}
                onNewMeetingTypeNameChange={setNewMeetingTypeName}
                onNewMeetingTypeDurationsChange={setNewMeetingTypeDurations}
                onAddMeetingType={() => void handleAddMeetingType()}
                onToggleMeetingType={(type) => void handleToggleMeetingType(type)}
              />
            ) : null}
            {activeTab === "profile" ? <ProfileScreen user={user} config={config} /> : null}
          </section>
        </>
      )}

      {toast ? <ToastMessage toast={toast} /> : null}
      {user.has_consent ? (
        <BottomNav tabs={visibleTabs} activeTab={activeTab} onChange={setActiveTab} />
      ) : null}
    </main>
  );
}

function Header({
  user,
  bookings,
  isPreview,
}: {
  user: MiniAppUser;
  bookings: MiniAppBooking[];
  isPreview: boolean;
}) {
  return (
    <>
      <section className="top-panel">
        <div>
          <p className="eyebrow">Ассистент встреч</p>
          <h1>{greeting(user)}</h1>
        </div>
        <div className="profile-chip">
          <span>{initials(user)}</span>
        </div>
      </section>
      {isPreview ? (
        <div className="notice">
          Предпросмотр вне Telegram. Авторизация, профиль и админ-доступ подключатся при открытии
          через Mini App.
        </div>
      ) : null}
      {nextConfirmedMeeting(bookings)?.meeting_url ? (
        <a className="meeting-link" href={nextConfirmedMeeting(bookings)?.meeting_url ?? "#"}>
          <LinkIcon size={18} aria-hidden="true" />
          <span>Ссылка на ближайшую встречу</span>
        </a>
      ) : null}
    </>
  );
}

function ConsentScreen({
  consentUrl,
  policyUrl,
  isBusy,
  onAccept,
}: {
  consentUrl: string | null | undefined;
  policyUrl: string | null | undefined;
  isBusy: boolean;
  onAccept: () => void;
}) {
  return (
    <section className="content-panel consent-panel">
      <div className="booking-icon">
        <ShieldCheck size={24} aria-hidden="true" />
      </div>
      <h2>Согласие на обработку данных</h2>
      <p>
        Для записи на встречу нужно подтвердить согласие одной кнопкой. Ссылки на документы
        доступны ниже.
      </p>
      <button type="button" className="primary-button" disabled={isBusy} onClick={onAccept}>
        {isBusy ? "Сохраняем..." : "Принимаю и продолжаю"}
      </button>
      <div className="legal-links">
        <a href={consentUrl ?? "#"} target="_blank" rel="noreferrer">
          Согласие на обработку
        </a>
        <a href={policyUrl ?? "#"} target="_blank" rel="noreferrer">
          Политика конфиденциальности
        </a>
      </div>
    </section>
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
  onChange,
  onStepChange,
  onSubmit,
}: {
  form: BookingFormState;
  formStep: FormStep;
  isBusy: boolean;
  meetingTypes: MiniAppMeetingType[];
  availableDates: string[];
  slots: MiniAppSlot[];
  activeBookingsCount: number;
  onChange: (next: BookingFormState) => void;
  onStepChange: (step: FormStep) => void;
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
          <button
            key={step}
            type="button"
            className={formStep === step ? "step step-active" : "step"}
            onClick={() => onStepChange(step)}
          >
            {index + 1}
          </button>
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
          <button
            type="button"
            className="primary-button"
            onClick={() => onStepChange("slot")}
            disabled={!form.fullName || !form.email || !form.meetingTypeId}
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
          <button
            type="button"
            className="primary-button"
            disabled={!form.slotKey || isBusy || activeLimitReached}
            onClick={() => onStepChange("review")}
          >
            Проверить заявку
          </button>
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
          <button type="button" className="primary-button" disabled={isBusy} onClick={onSubmit}>
            {isBusy ? "Отправляем..." : form.previousBookingId ? "Отправить перенос" : "Отправить заявку"}
          </button>
        </div>
      ) : null}
    </>
  );
}

function BookingsScreen({
  bookings,
  selectedBooking,
  cancelReason,
  isBusy,
  onSelect,
  onCancelReasonChange,
  onCancel,
  onReschedule,
}: {
  bookings: MiniAppBooking[];
  selectedBooking: MiniAppBooking | null;
  cancelReason: string;
  isBusy: boolean;
  onSelect: (booking: MiniAppBooking | null) => void;
  onCancelReasonChange: (value: string) => void;
  onCancel: (booking: MiniAppBooking) => void;
  onReschedule: (booking: MiniAppBooking) => void;
}) {
  return (
    <>
      <PanelHeader title="Мои заявки" action={`${bookings.length}`} />
      <div className="timeline-list">
        {(bookings.length ? bookings : previewBookings()).map((booking) => (
          <button
            key={booking.id}
            type="button"
            className="booking-row booking-row-button"
            onClick={() => onSelect(booking)}
          >
            <div>
              <strong>{statusLabel(booking.status)}</strong>
              <span>{dateTimeLabel(booking.starts_at)}</span>
            </div>
            {booking.meeting_url ? <LinkIcon size={20} aria-hidden="true" /> : <CheckCircle2 size={20} aria-hidden="true" />}
          </button>
        ))}
      </div>

      {selectedBooking ? (
        <div className="detail-panel">
          <PanelHeader title="Карточка заявки" action={statusLabel(selectedBooking.status)} />
          <ReviewRow label="Дата" value={dateTimeLabel(selectedBooking.starts_at)} />
          <ReviewRow label="Длительность" value={`${selectedBooking.duration_minutes} минут`} />
          <ReviewRow label="Комментарий" value={selectedBooking.user_comment || "Без комментария"} />
          {selectedBooking.meeting_url ? (
            <a className="meeting-link inline-link" href={selectedBooking.meeting_url} target="_blank" rel="noreferrer">
              <LinkIcon size={18} aria-hidden="true" />
              Google Meet / Calendar
            </a>
          ) : null}
          {isCancellable(selectedBooking) ? (
            <label className="wide-field">
              <span>Причина отмены</span>
              <textarea
                value={cancelReason}
                onChange={(event) => onCancelReasonChange(event.target.value)}
                placeholder="Можно оставить пустым"
              />
            </label>
          ) : null}
          <div className="action-row">
            {isCancellable(selectedBooking) ? (
              <button type="button" className="danger-button" disabled={isBusy} onClick={() => onCancel(selectedBooking)}>
                <XCircle size={18} aria-hidden="true" />
                Отменить
              </button>
            ) : null}
            {isReschedulable(selectedBooking) ? (
              <button type="button" className="secondary-button" disabled={isBusy} onClick={() => onReschedule(selectedBooking)}>
                <RefreshCw size={18} aria-hidden="true" />
                Перенести
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}

function CalendarScreen({ bookings }: { bookings: MiniAppBooking[] }) {
  const upcoming = bookings
    .filter((booking) => ["pending", "confirmed", "reschedule_requested"].includes(booking.status))
    .sort((left, right) => left.starts_at.localeCompare(right.starts_at));

  return (
    <>
      <PanelHeader title="Календарь" action="План" />
      <div className="calendar-card">
        {previewDates().slice(0, 5).map((date, index) => (
          <div key={date} className={index === 2 ? "calendar-day selected" : "calendar-day"}>
            <span>{weekdayLabel(date)}</span>
            <strong>{dayLabel(date)}</strong>
          </div>
        ))}
      </div>
      <div className="timeline-list compact-list">
        {upcoming.slice(0, 4).map((booking) => (
          <div key={booking.id} className="booking-row">
            <div>
              <strong>{statusLabel(booking.status)}</strong>
              <span>{dateTimeLabel(booking.starts_at)}</span>
            </div>
            <Clock3 size={18} aria-hidden="true" />
          </div>
        ))}
      </div>
    </>
  );
}

function ProfileScreen({ user, config }: { user: MiniAppUser; config: MiniAppConfig | null }) {
  return (
    <>
      <PanelHeader title="Профиль" action={user.is_admin ? "Админ" : "Пользователь"} />
      <div className="profile-panel">
        <div className="profile-avatar">{initials(user)}</div>
        <div>
          <strong>{user.full_name || user.telegram_username || "Пользователь"}</strong>
          <span>{user.has_consent ? "Согласие принято" : "Согласие ожидается"}</span>
        </div>
      </div>
      <div className="legal-links profile-links">
        <a href={config?.consent_url ?? "#"} target="_blank" rel="noreferrer">
          Согласие на обработку
        </a>
        <a href={config?.policy_url ?? "#"} target="_blank" rel="noreferrer">
          Политика конфиденциальности
        </a>
      </div>
    </>
  );
}

function AdminScreen({
  view,
  dashboard,
  cards,
  calendar,
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
  onNewClosedDayChange,
  onNewClosedDayCommentChange,
  onAddClosedDay,
  onNewClosedHoursDateChange,
  onNewClosedHoursStartChange,
  onNewClosedHoursEndChange,
  onNewClosedHoursCommentChange,
  onAddClosedHours,
  onDeleteRestriction,
  onNewMeetingTypeNameChange,
  onNewMeetingTypeDurationsChange,
  onAddMeetingType,
  onToggleMeetingType,
}: {
  view: AdminView;
  dashboard: MiniAppAdminDashboard | null;
  cards: MiniAppAdminBookingCard[];
  calendar: MiniAppBooking[];
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
  onNewClosedDayChange: (value: string) => void;
  onNewClosedDayCommentChange: (value: string) => void;
  onAddClosedDay: () => void;
  onNewClosedHoursDateChange: (value: string) => void;
  onNewClosedHoursStartChange: (value: string) => void;
  onNewClosedHoursEndChange: (value: string) => void;
  onNewClosedHoursCommentChange: (value: string) => void;
  onAddClosedHours: () => void;
  onDeleteRestriction: (id: string) => void;
  onNewMeetingTypeNameChange: (value: string) => void;
  onNewMeetingTypeDurationsChange: (value: string) => void;
  onAddMeetingType: () => void;
  onToggleMeetingType: (type: MiniAppAdminMeetingType) => void;
}) {
  return (
    <>
      <PanelHeader title="Админ" action="Mini App" />
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
      {view === "dashboard" ? <AdminDashboardView dashboard={dashboard} /> : null}
      {view === "requests" ? (
        <AdminRequestsView
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
        />
      ) : null}
      {view === "calendar" ? <AdminCalendarView bookings={calendar} /> : null}
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
  { id: "dashboard", label: "Сводка" },
  { id: "requests", label: "Заявки" },
  { id: "calendar", label: "План" },
  { id: "schedule", label: "Расписание" },
  { id: "types", label: "Типы" },
];

function AdminDashboardView({ dashboard }: { dashboard: MiniAppAdminDashboard | null }) {
  const metrics = dashboard?.metrics;
  return (
    <>
      <div className="admin-grid">
        <AdminTile label="Ожидают" value={String(metrics?.pending ?? 0)} />
        <AdminTile label="Подтверждены" value={String(metrics?.confirmed ?? 0)} />
        <AdminTile label="Переносы" value={String(metrics?.reschedule_requested ?? 0)} />
        <AdminTile label="Отменены" value={String(metrics?.cancelled ?? 0)} />
      </div>
      <div className="detail-panel">
        <PanelHeader title="Ближайшие" action={`${dashboard?.upcoming.length ?? 0}`} />
        {(dashboard?.upcoming ?? []).slice(0, 4).map((booking) => (
          <div key={booking.id} className="booking-row">
            <div>
              <strong>{statusLabel(booking.status)}</strong>
              <span>{dateTimeLabel(booking.starts_at)}</span>
            </div>
            <Clock3 size={18} aria-hidden="true" />
          </div>
        ))}
      </div>
    </>
  );
}

function AdminRequestsView({
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
}: {
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
}) {
  return (
    <>
      <select
        className="admin-filter"
        value={statusFilter}
        onChange={(event) => onStatusFilterChange(event.target.value as AdminStatusFilter)}
      >
        <option value="">Все</option>
        <option value="pending">Ожидают</option>
        <option value="confirmed">Подтверждены</option>
        <option value="reschedule_requested">Переносы</option>
        <option value="rejected">Отклонены</option>
      </select>
      <div className="timeline-list">
        {cards.map((card) => (
          <button
            key={card.booking.id}
            type="button"
            className="booking-row booking-row-button"
            onClick={() => onSelectCard(card)}
          >
            <div>
              <strong>{card.user.full_name || card.user.telegram_username || "Пользователь"}</strong>
              <span>
                {statusLabel(card.booking.status)} · {dateTimeLabel(card.booking.starts_at)}
              </span>
            </div>
            <span>{card.meeting_type.name}</span>
          </button>
        ))}
      </div>
      {selectedCard ? (
        <div className="detail-panel">
          <PanelHeader title="Заявка" action={statusLabel(selectedCard.booking.status)} />
          <ReviewRow label="Клиент" value={selectedCard.user.full_name || "Без имени"} />
          <ReviewRow label="Email" value={selectedCard.user.email || "Не указан"} />
          <ReviewRow label="Тип" value={selectedCard.meeting_type.name} />
          <ReviewRow label="Время" value={dateTimeLabel(selectedCard.booking.starts_at)} />
          <ReviewRow label="Комментарий" value={selectedCard.booking.user_comment || "Без комментария"} />
          {selectedCard.booking.status === "pending" ? (
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
                  onClick={() => onConfirm(selectedCard)}
                >
                  <CheckCircle2 size={18} aria-hidden="true" />
                  Подтвердить
                </button>
                <button
                  type="button"
                  className="danger-button"
                  disabled={isBusy}
                  onClick={() => onReject(selectedCard)}
                >
                  <XCircle size={18} aria-hidden="true" />
                  Отклонить
                </button>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function AdminCalendarView({ bookings }: { bookings: MiniAppBooking[] }) {
  return (
    <>
      <div className="calendar-card">
        {previewDates().slice(0, 5).map((date, index) => (
          <div key={date} className={index === 1 ? "calendar-day selected" : "calendar-day"}>
            <span>{weekdayLabel(date)}</span>
            <strong>{dayLabel(date)}</strong>
          </div>
        ))}
      </div>
      <div className="timeline-list compact-list">
        {bookings.map((booking) => (
          <div key={booking.id} className="booking-row">
            <div>
              <strong>{dateTimeLabel(booking.starts_at)}</strong>
              <span>{booking.meeting_url ? "Meet ссылка есть" : "Без ссылки"}</span>
            </div>
            <CalendarDays size={18} aria-hidden="true" />
          </div>
        ))}
      </div>
    </>
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
}) {
  return (
    <>
      <div className="admin-grid">
        <AdminTile label="Часовой пояс" value={settings?.timezone ?? "Не задан"} />
        <AdminTile label="Горизонт" value={`${settings?.booking_horizon_days ?? 0} дней`} />
        <AdminTile label="Шаг слота" value={`${settings?.slot_step_minutes ?? 0} мин`} />
        <AdminTile label="Буфер" value={`${settings?.meeting_buffer_minutes ?? 0} мин`} />
      </div>
      <div className="detail-panel">
        <PanelHeader title="Рабочие часы" action={`${workingHours.length}`} />
        {workingHours.map((row) => (
          <ReviewRow
            key={row.weekday}
            label={weekdayName(row.weekday)}
            value={row.is_working_day ? `${row.start_time} - ${row.end_time}` : "Выходной"}
          />
        ))}
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
          <label className="wide-field">
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
          <label className="wide-field">
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

function PanelHeader({ title, action }: { title: string; action: string }) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      <span>{action}</span>
    </div>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "green" | "purple" | "peach";
}) {
  return (
    <article className={`metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
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

function AdminTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="admin-tile">
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

function greeting(user: MiniAppUser): string {
  const name = user.full_name || user.telegram_username || "гость";
  return `Здравствуйте, ${name}`;
}

function initials(user: MiniAppUser): string {
  const source = user.full_name || user.telegram_username || "MA";
  return source
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function activeBookings(bookings: MiniAppBooking[]): number {
  return bookings.filter((booking) =>
    ["pending", "confirmed", "reschedule_requested"].includes(booking.status),
  ).length;
}

function pendingBookings(bookings: MiniAppBooking[]): number {
  return bookings.filter((booking) => booking.status === "pending").length;
}

function nextBookingLabel(bookings: MiniAppBooking[]): string {
  const next = nextConfirmedMeeting(bookings);
  return next ? dateLabel(next.starts_at) : "Нет";
}

function nextConfirmedMeeting(bookings: MiniAppBooking[]): MiniAppBooking | null {
  return (
    bookings
      .filter((booking) => booking.status === "confirmed")
      .sort((left, right) => left.starts_at.localeCompare(right.starts_at))[0] ?? null
  );
}

function isCancellable(booking: MiniAppBooking): boolean {
  return ["pending", "confirmed"].includes(booking.status);
}

function isReschedulable(booking: MiniAppBooking): boolean {
  return booking.status === "confirmed";
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

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
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
