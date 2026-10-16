from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Doctor
from .views import API_ROLES, Role

# Close codes the frontend can react to (4000-4999 is the application range).
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403


def doctor_group_name(user_id):
    """Channel-layer group for one doctor's dashboard. notifications.py must use
    this same helper when sending, so the two names can never drift apart."""
    return f'doctor-{user_id}'


class DoctorDashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self._reject(CLOSE_UNAUTHENTICATED)
            return

        if not await self._is_linked_doctor(user):
            await self._reject(CLOSE_FORBIDDEN)
            return

        self.group_name = doctor_group_name(user.pk)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def _reject(self, code):
        # Closing before accept() rejects the handshake with a plain HTTP 403, and
        # the browser never sees the custom code. Accept first, then close, so the
        # frontend can tell "log in again" (4401) from "not allowed" (4403).
        await self.accept()
        await self.close(code=code)

    async def _is_linked_doctor(self, user):
        # Same rule as the REST API (_api_role): exactly one portal role, and it
        # must be Doctor. A superuser counts as Admin, not Doctor.
        if user.is_superuser:
            return False
        roles = [
            name async for name in
            user.groups.filter(name__in=API_ROLES).values_list('name', flat=True)
        ]
        if roles != [Role.DOCTOR]:
            return False
        # A Doctor-role account with no linked doctor profile has no dashboard.
        return await Doctor.objects.filter(user=user).aexists()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # The dashboard socket is server-push only; ignore anything clients send.
        return

    async def dashboard_event(self, event):
        event_type = event.get('event_type')
        if isinstance(event_type, str) and event_type:
            await self.send_json({'type': event_type})