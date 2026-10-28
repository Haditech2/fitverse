import json

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from fitverse_app.models import UserMeasurement
from fitverse_app.services.bodygram import BodygramError, fetch_scan


class Command(BaseCommand):
    help = (
        "Refresh saved measurements from an existing Bodygram scan. Reading a scan "
        "does not consume Bodygram quota."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'scan_id',
            nargs='?',
            help="Bodygram scan ID. Defaults to the latest scan saved on a measurement profile.",
        )
        parser.add_argument(
            '--profile-id',
            type=int,
            help="UserMeasurement row to update. Defaults to the most recently updated row.",
        )

    def handle(self, *args, **options):
        scan_id = options.get('scan_id')
        profile_id = options.get('profile_id')

        queryset = UserMeasurement.objects.all()
        if profile_id:
            profile = queryset.filter(pk=profile_id).first()
            if not profile:
                raise CommandError(f"No measurement profile with id {profile_id}.")
        else:
            profile = queryset.order_by('-updated_at').first()
            if not profile:
                raise CommandError("No measurement profiles exist yet.")

        scan_id = scan_id or profile.bodygram_scan_id
        if not scan_id:
            raise CommandError(
                "No Bodygram scan ID given and the selected profile has none. "
                "Pass a scan ID, e.g. `manage.py refresh_bodygram_scan scan_abc123`."
            )

        try:
            result = fetch_scan(scan_id)
        except BodygramError as exc:
            raise CommandError(str(exc)) from exc

        for field, value in result['measurements'].items():
            setattr(profile, field, value)
        for field, value in (result.get('stats') or {}).items():
            setattr(profile, field, value)
        profile.unit = 'cm'
        profile.bodygram_scan_id = result['scan_id'] or scan_id
        profile.bodygram_measurements = result['all_measurements']
        profile.body_composition = result['body_composition'] or {}
        profile.bodygram_posture = result['posture'] or {}
        if result.get('avatar_obj'):
            name = f"{result['scan_id'] or scan_id}.obj"
            storage = profile.bodygram_avatar.storage
            if storage.exists(name):
                profile.bodygram_avatar.name = name
            else:
                if profile.bodygram_avatar:
                    profile.bodygram_avatar.delete(save=False)
                profile.bodygram_avatar.save(
                    name,
                    ContentFile(result['avatar_obj']),
                    save=False,
                )
        profile.bodygram_scanned_at = timezone.now()
        profile.save()

        self.stdout.write(self.style.SUCCESS(
            f"Refresh complete for {profile.bodygram_scan_id}: "
            f"{len(result['measurements'])} tailoring measurements, "
            f"{len(result['all_measurements'])} total."
        ))
        self.stdout.write(json.dumps(result['measurements'], indent=2))
