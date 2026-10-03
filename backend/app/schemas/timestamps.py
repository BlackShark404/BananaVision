"""Timestamp contracts for incoming local forms and outgoing stored instants."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator

from app.core.time import as_manila, input_manila

Timestamp = Annotated[datetime, AfterValidator(as_manila)]
InputTimestamp = Annotated[datetime, AfterValidator(input_manila)]
