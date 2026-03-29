"""initial schema - all core tables.

Revision ID: 001
Revises: 
Create Date: 2026-02-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry


# revision identifiers
revision: str = '20260209_0600_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- enums ---
    verification_status = postgresql.ENUM(
        'pending', 'verified', 'rejected', 'suspended',
        name='verification_status'
    )
    verification_status.create(op.get_bind(), checkfirst=True)
    
    driver_status = postgresql.ENUM(
        'available', 'on_delivery', 'offline',
        name='driver_status'
    )
    driver_status.create(op.get_bind(), checkfirst=True)
    
    fuel_type = postgresql.ENUM(
        'diesel', 'petrol', 'paraffin',
        name='fuel_type'
    )
    fuel_type.create(op.get_bind(), checkfirst=True)
    
    order_status = postgresql.ENUM(
        'pending', 'confirmed', 'dispatched', 'delivered', 'cancelled',
        name='order_status'
    )
    order_status.create(op.get_bind(), checkfirst=True)
    
    assignment_status = postgresql.ENUM(
        'assigned', 'en_route', 'arrived', 'completed', 'failed',
        name='assignment_status'
    )
    assignment_status.create(op.get_bind(), checkfirst=True)
    
    # --- shop_profiles ---
    op.create_table(
        'shop_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('phone_number', sa.String(20), unique=True, index=True, nullable=False),
        sa.Column('business_name', sa.String(255), nullable=False),
        sa.Column('contact_name', sa.String(255), nullable=True),
        sa.Column('default_location', Geometry('POINT', srid=4326), nullable=True),
        sa.Column('verification_status', verification_status, default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    
    # --- depots ---
    op.create_table(
        'depots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone_number', sa.String(20), unique=True, index=True, nullable=False),
        sa.Column('location', Geometry('POINT', srid=4326), nullable=False),
        sa.Column('fuel_types_available', postgresql.ARRAY(sa.String(50)), default=list),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    
    # --- drivers ---
    op.create_table(
        'drivers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('depot_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('depots.id'), index=True, nullable=False),
        sa.Column('phone_number', sa.String(20), unique=True, index=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('vehicle_plate', sa.String(20), nullable=False),
        sa.Column('status', driver_status, default='offline', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    
    # --- orders ---
    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_number', sa.String(20), unique=True, index=True, nullable=False),
        sa.Column('shop_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('shop_profiles.id'), nullable=False),
        sa.Column('depot_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('depots.id'), nullable=True),
        sa.Column('fuel_type', fuel_type, nullable=False),
        sa.Column('quantity_liters', sa.Numeric(10, 2), nullable=False),
        sa.Column('delivery_location', Geometry('POINT', srid=4326), nullable=False),
        sa.Column('quoted_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('status', order_status, default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    
    # --- delivery_assignments ---
    op.create_table(
        'delivery_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id'), unique=True, nullable=False),
        sa.Column('driver_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('drivers.id'), index=True, nullable=False),
        sa.Column('status', assignment_status, default='assigned', nullable=False),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completion_notes', sa.Text(), nullable=True),
        sa.Column('proof_of_delivery_url', sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('delivery_assignments')
    op.drop_table('orders')
    op.drop_table('drivers')
    op.drop_table('depots')
    op.drop_table('shop_profiles')
    
    # drop enums
    op.execute('DROP TYPE IF EXISTS assignment_status')
    op.execute('DROP TYPE IF EXISTS order_status')
    op.execute('DROP TYPE IF EXISTS fuel_type')
    op.execute('DROP TYPE IF EXISTS driver_status')
    op.execute('DROP TYPE IF EXISTS verification_status')
