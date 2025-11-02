# participants/management/commands/import_participants.py
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from participants.models import Participant
import pandas as pd

class Command(BaseCommand):
    help = 'Import participants from Excel file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to Excel file')

    def handle(self, *args, **options):
        file_path = options['file_path']
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()

        required = ["Full Name", "Nationality", "Paid"]
        for col in required:
            if col not in df.columns:
                self.stdout.write(self.style.ERROR(f"Missing column: {col}"))
                return

        created = 0
        with transaction.atomic():
            for _, row in df.iterrows():
                full_name = str(row["Full Name"]).strip()
                nationality = str(row["Nationality"]).strip()
                paid = str(row["Paid"]).strip().lower() in ["yes", "true", "1", "paid"]

                obj, new = Participant.objects.get_or_create(
                    full_name=full_name,
                    nationality=nationality,
                    defaults={'paid': paid}
                )
                if new:
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Imported {created} new participants.")
        )