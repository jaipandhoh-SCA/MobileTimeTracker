"""add estimating: assembly_items, estimate_templates, estimates, line items

Revision ID: b3e2d9f41c05
Revises: a2f1c8e30b91
Create Date: 2026-08-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e2d9f41c05'
down_revision: Union[str, None] = 'a2f1c8e30b91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Assembly Items (cost/assembly DB) ---
    op.create_table('assembly_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('unit', sa.String(20), nullable=False, server_default='EA'),
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('labor_pct', sa.Numeric(5, 2), nullable=False, server_default='50'),
        sa.Column('material_pct', sa.Numeric(5, 2), nullable=False, server_default='50'),
        sa.Column('waste_pct', sa.Numeric(5, 2), nullable=False, server_default='5'),
        sa.Column('default_qty', sa.Numeric(10, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_assembly_cost_code', 'assembly_items', ['cost_code_id'])

    # --- Estimate Templates ---
    op.create_table('estimate_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('adu_type', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('default_sqft', sa.Integer(), nullable=True),
        sa.Column('default_markup_pct', sa.Numeric(5, 2), nullable=False, server_default='15'),
        sa.Column('default_overhead_pct', sa.Numeric(5, 2), nullable=False, server_default='10'),
        sa.Column('default_contingency_pct', sa.Numeric(5, 2), nullable=False, server_default='5'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # --- Estimate Template Items ---
    op.create_table('estimate_template_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('estimate_templates.id'), nullable=False),
        sa.Column('assembly_item_id', sa.Integer(), sa.ForeignKey('assembly_items.id'), nullable=False),
        sa.Column('default_qty', sa.Numeric(10, 2), nullable=False, server_default='1'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('idx_eti_template', 'estimate_template_items', ['template_id'])

    # --- Estimates ---
    op.create_table('estimates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('estimate_templates.id'), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='Draft'),
        sa.Column('adu_type', sa.String(50), nullable=True),
        sa.Column('sqft', sa.Integer(), nullable=True),
        sa.Column('markup_pct', sa.Numeric(5, 2), nullable=False, server_default='15'),
        sa.Column('overhead_pct', sa.Numeric(5, 2), nullable=False, server_default='10'),
        sa.Column('contingency_pct', sa.Numeric(5, 2), nullable=False, server_default='5'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_estimate_client', 'estimates', ['client_id'])

    # --- Estimate Line Items ---
    op.create_table('estimate_line_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('estimate_id', sa.Integer(), sa.ForeignKey('estimates.id'), nullable=False),
        sa.Column('cost_code_id', sa.Integer(), sa.ForeignKey('cost_codes.id'), nullable=False),
        sa.Column('assembly_item_id', sa.Integer(), sa.ForeignKey('assembly_items.id'), nullable=True),
        sa.Column('description', sa.String(300), nullable=False),
        sa.Column('unit', sa.String(20), nullable=False, server_default='EA'),
        sa.Column('qty', sa.Numeric(10, 2), nullable=False, server_default='1'),
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('labor_pct', sa.Numeric(5, 2), nullable=False, server_default='50'),
        sa.Column('material_pct', sa.Numeric(5, 2), nullable=False, server_default='50'),
        sa.Column('waste_pct', sa.Numeric(5, 2), nullable=False, server_default='5'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_eli_estimate', 'estimate_line_items', ['estimate_id'])

    # --- Seed assembly items ---
    _seed_assembly_items()
    _seed_estimate_templates()


def _seed_assembly_items():
    """Seed the ADU cost database with typical line items by cost code."""
    conn = op.get_bind()
    # Get cost code IDs by code
    codes = {}
    for row in conn.execute(sa.text("SELECT id, code FROM cost_codes")):
        codes[row[1]] = row[0]

    # Cost codes: 01=Site, 02=Foundation, 03=Framing, 04=Plumbing, 05=Electrical,
    # 06=HVAC, 07=Insulation&Drywall, 08=Roofing, 09=Exterior, 10=Interior,
    # 10.1=Flooring, 10.2=Cabinets, 10.3=Paint, 11=Windows&Doors,
    # 12=Permits, 13=Design, 14=Utilities, 15=General Conditions, 16=Cleanup
    items = [
        ('01', 'Site Clearing & Grading', 'Clear, grade, and compact building pad', 'SF', 3.50, 60, 40, 5, 400),
        ('01', 'Utility Trenching', 'Trenching for water, sewer, electrical', 'LF', 25.00, 70, 30, 0, 80),
        ('01', 'Concrete Driveway/Path', 'Concrete flatwork for access', 'SF', 12.00, 40, 60, 5, 200),
        ('02', 'Slab-on-Grade Foundation', 'Reinforced concrete slab with footings', 'SF', 18.00, 45, 55, 5, 400),
        ('02', 'Raised Foundation', 'Perimeter stem wall + piers', 'SF', 28.00, 50, 50, 5, 400),
        ('02', 'Foundation Waterproofing', 'Below-grade waterproofing membrane', 'SF', 4.50, 60, 40, 10, 400),
        ('03', 'Wall Framing Package', 'Exterior + interior wall framing lumber + labor', 'SF', 22.00, 55, 45, 10, 400),
        ('03', 'Roof Framing / Trusses', 'Engineered trusses or conventional roof framing', 'SF', 14.00, 50, 50, 10, 400),
        ('03', 'Sheathing (Walls + Roof)', 'OSB/plywood structural sheathing', 'SF', 5.50, 40, 60, 10, 800),
        ('08', 'Asphalt Shingle Roofing', 'Architectural shingles + underlayment', 'SQ', 350.00, 50, 50, 10, 5),
        ('08', 'Standing Seam Metal Roof', 'Metal roofing panels + flashing', 'SQ', 750.00, 45, 55, 5, 5),
        ('08', 'Gutters & Downspouts', 'Seamless aluminum gutters', 'LF', 12.00, 55, 45, 5, 80),
        ('04', 'Rough-In Plumbing', 'Supply + DWV rough-in (kitchen + 1 bath)', 'EA', 4500.00, 65, 35, 0, 1),
        ('04', 'Plumbing Fixtures', 'Toilet, vanity, shower, kitchen sink', 'EA', 2500.00, 30, 70, 0, 1),
        ('04', 'Water Heater', 'Tankless or 40-gal tank, installed', 'EA', 1800.00, 40, 60, 0, 1),
        ('05', 'Electrical Rough-In', 'Panel, circuits, boxes, wiring', 'EA', 5000.00, 70, 30, 0, 1),
        ('05', 'Electrical Finish', 'Devices, fixtures, switches, outlets', 'EA', 2500.00, 50, 50, 0, 1),
        ('05', 'Service Upgrade / Sub-panel', '200A or sub-panel from main', 'EA', 3500.00, 65, 35, 0, 1),
        ('06', 'Mini-Split Heat Pump', 'Ductless mini-split system, installed', 'EA', 4500.00, 45, 55, 0, 1),
        ('06', 'Bath Exhaust Fan', 'Exhaust fan vented to exterior', 'EA', 350.00, 50, 50, 0, 1),
        ('06', 'Range Hood Vent', 'Kitchen range hood and ductwork', 'EA', 600.00, 45, 55, 0, 1),
        ('07', 'Wall Insulation (R-21)', 'Fiberglass batt or blown-in walls', 'SF', 2.80, 40, 60, 5, 400),
        ('07', 'Ceiling Insulation (R-38)', 'Blown-in attic/ceiling insulation', 'SF', 3.50, 35, 65, 5, 400),
        ('07', 'Drywall Package', 'Complete drywall package', 'SF', 5.00, 65, 35, 5, 1200),
        ('09', 'Siding - HardiePlank', 'Fiber cement lap siding installed', 'SF', 12.00, 55, 45, 10, 600),
        ('11', 'Exterior Windows', 'Vinyl or aluminum dual-pane windows', 'EA', 650.00, 35, 65, 0, 6),
        ('11', 'Exterior Door - Entry', 'Insulated entry door, installed', 'EA', 1200.00, 35, 65, 0, 1),
        ('11', 'Sliding Glass Door', 'Dual-pane sliding patio door', 'EA', 1800.00, 35, 65, 0, 1),
        ('10', 'Interior Doors', 'Hollow-core interior doors, installed', 'EA', 350.00, 40, 60, 0, 4),
        ('10', 'Trim & Baseboard', 'Baseboards + window/door casing', 'LF', 8.00, 55, 45, 10, 200),
        ('10.3', 'Interior Paint', 'Primer + 2 coats, walls + ceiling', 'SF', 3.50, 70, 30, 5, 1200),
        ('10.1', 'LVP Flooring', 'Luxury vinyl plank + underlayment', 'SF', 7.50, 40, 60, 10, 400),
        ('10.1', 'Tile Flooring (Bath)', 'Porcelain tile, bathroom', 'SF', 14.00, 55, 45, 10, 50),
        ('10.2', 'Kitchen Cabinets', 'Stock or semi-custom cabinets, installed', 'LF', 250.00, 35, 65, 0, 12),
        ('10.2', 'Kitchen Countertop', 'Quartz or granite countertop, installed', 'SF', 75.00, 30, 70, 5, 30),
        ('10.2', 'Bathroom Vanity', 'Vanity + top, installed', 'EA', 800.00, 30, 70, 0, 1),
        ('10', 'Refrigerator', 'Standard apartment-size refrigerator', 'EA', 900.00, 10, 90, 0, 1),
        ('10', 'Range / Cooktop', 'Electric or gas range', 'EA', 700.00, 10, 90, 0, 1),
        ('10', 'Dishwasher', 'Standard built-in dishwasher', 'EA', 550.00, 15, 85, 0, 1),
        ('10', 'Washer/Dryer (Stackable)', 'Compact stackable washer/dryer', 'EA', 1600.00, 10, 90, 0, 1),
        ('12', 'Building Permit', 'City/county building permit', 'LS', 5000.00, 0, 100, 0, 1),
        ('12', 'Plan Check Fee', 'Plan check and review fees', 'LS', 2500.00, 0, 100, 0, 1),
        ('12', 'Impact / School Fees', 'Development impact fees', 'LS', 3000.00, 0, 100, 0, 1),
        ('13', 'Architectural Plans', 'Complete ADU plan set', 'LS', 5000.00, 100, 0, 0, 1),
        ('13', 'Engineering (Structural)', 'Structural engineering calcs + stamp', 'LS', 2500.00, 100, 0, 0, 1),
        ('13', 'Title 24 Energy Report', 'California energy compliance', 'LS', 800.00, 100, 0, 0, 1),
        ('05', 'Smoke / CO Detectors', 'Hard-wired smoke + CO detectors', 'EA', 150.00, 50, 50, 0, 4),
        ('04', 'Fire Sprinkler System', 'Residential fire sprinkler system', 'SF', 6.00, 60, 40, 5, 400),
        ('14', 'Sewer Connection', 'Sewer lateral connection to main', 'EA', 4000.00, 60, 40, 0, 1),
        ('14', 'Water Connection', 'Water service tap and meter', 'EA', 3500.00, 55, 45, 0, 1),
        ('15', 'Dumpster / Debris Removal', 'Construction dumpster rental + hauling', 'EA', 1500.00, 20, 80, 0, 2),
        ('15', 'Temporary Facilities', 'Temp power, toilet, fencing', 'LS', 2000.00, 30, 70, 0, 1),
        ('16', 'Final Clean', 'Construction final cleaning', 'LS', 800.00, 80, 20, 0, 1),
        ('01', 'Basic Landscaping', 'Grading, seed/sod, basic planting', 'SF', 4.00, 60, 40, 5, 200),
        ('01', 'Hardscape (Walkway/Patio)', 'Concrete or paver patio/walkway', 'SF', 15.00, 50, 50, 5, 100),
    ]

    sort = 0
    for code, name, desc, unit, cost, labor, material, waste, qty in items:
        cc_id = codes.get(code)
        if not cc_id:
            continue
        sort += 10
        conn.execute(sa.text(
            "INSERT INTO assembly_items (cost_code_id, name, description, unit, unit_cost, "
            "labor_pct, material_pct, waste_pct, default_qty, sort_order) "
            "VALUES (:cc, :name, :desc, :unit, :cost, :labor, :mat, :waste, :qty, :sort)"
        ), {
            'cc': cc_id, 'name': name, 'desc': desc, 'unit': unit,
            'cost': cost, 'labor': labor, 'mat': material, 'waste': waste,
            'qty': qty, 'sort': sort,
        })


def _seed_estimate_templates():
    """Create ADU estimate templates with typical line items."""
    conn = op.get_bind()

    templates = [
        ('Studio ADU (400 SF)', 'Studio', 'Compact studio ADU', 400, 15, 10, 5),
        ('1-Bedroom ADU (500 SF)', '1BR', 'Separate bedroom, full kitchen, bath', 500, 15, 10, 5),
        ('2-Bedroom ADU (750 SF)', '2BR', 'Two bedrooms, full kitchen, bath', 750, 15, 10, 5),
        ('Detached ADU (600 SF)', 'Detached', 'Ground-up detached structure', 600, 15, 10, 5),
        ('Garage Conversion (400 SF)', 'Garage Conversion', 'Convert existing garage to living', 400, 12, 8, 5),
    ]

    for name, adu_type, desc, sqft, markup, overhead, contingency in templates:
        conn.execute(sa.text(
            "INSERT INTO estimate_templates (name, adu_type, description, default_sqft, "
            "default_markup_pct, default_overhead_pct, default_contingency_pct) "
            "VALUES (:name, :adu_type, :desc, :sqft, :markup, :overhead, :cont)"
        ), {
            'name': name, 'adu_type': adu_type, 'desc': desc, 'sqft': sqft,
            'markup': markup, 'overhead': overhead, 'cont': contingency,
        })

    # Link assembly items to templates — garage conversion skips foundation/framing heavy items
    # Get all template IDs
    tpl_rows = conn.execute(sa.text("SELECT id, adu_type FROM estimate_templates")).fetchall()
    tpls = {r[1]: r[0] for r in tpl_rows}

    # Get all assembly items
    asm_rows = conn.execute(sa.text(
        "SELECT ai.id, ai.cost_code_id, ai.default_qty, ai.sort_order, cc.code "
        "FROM assembly_items ai JOIN cost_codes cc ON cc.id = ai.cost_code_id "
        "ORDER BY ai.sort_order"
    )).fetchall()

    # Garage conversion exclusions — skip heavy structural items
    garage_skip_names = {'Slab-on-Grade Foundation', 'Raised Foundation', 'Foundation Waterproofing',
                         'Wall Framing Package', 'Roof Framing / Trusses', 'Sheathing (Walls + Roof)',
                         'Asphalt Shingle Roofing', 'Standing Seam Metal Roof'}
    asm_names = {r[0]: conn.execute(sa.text("SELECT name FROM assembly_items WHERE id = :id"), {'id': r[0]}).scalar()
                 for r in asm_rows}

    for adu_type, tpl_id in tpls.items():
        sort = 0
        for asm_id, cc_id, default_qty, asm_sort, cc_code in asm_rows:
            item_name = asm_names.get(asm_id, '')
            # Garage conversion: skip structural items that already exist
            if adu_type == 'Garage Conversion' and item_name in garage_skip_names:
                continue
            sort += 10
            conn.execute(sa.text(
                "INSERT INTO estimate_template_items (template_id, assembly_item_id, default_qty, sort_order) "
                "VALUES (:tpl, :asm, :qty, :sort)"
            ), {'tpl': tpl_id, 'asm': asm_id, 'qty': default_qty or 1, 'sort': sort})


def downgrade() -> None:
    op.drop_table('estimate_line_items')
    op.drop_table('estimates')
    op.drop_table('estimate_template_items')
    op.drop_table('estimate_templates')
    op.drop_table('assembly_items')
