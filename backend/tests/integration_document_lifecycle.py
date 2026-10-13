"""Runs only against disposable network-none PostgreSQL clone."""
import asyncio
import uuid
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.exc import DBAPIError
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.dependencies import TokenData
from app.models.document_snapshot import DocumentSnapshot, DocumentEvent
from app.models.purchase import PurchaseOrder, GoodsReceipt
from app.models.payable import SupplierInvoice
from app.models.company import Company
from app.models.etax import TaxDocument
from app.schemas.purchase import CreatePORequest, POItemCreate, UpdatePORequest, ApprovePORequest, CreateGRRequest, GRItemCreate
from app.schemas.etax import IssueTaxInvoiceRequest, IssueCreditNoteRequest, CancelDocumentRequest
from app.schemas.payable import SupplierInvoiceCreate
from app.services.purchase_service import PurchaseService
from app.services.etax_service import ETaxService
from app.services.payable_service import PayableService
from app.services.document_archive_service import history, export_document, evidence_for
from app.services.document_snapshot_service import snapshot_digest
from app.routers.purchase import replace_purchase_order, ReplacementRequest
from app.utils.pdf_generator import html_to_pdf_or_html

assert settings.database_url == 'postgresql+asyncpg://unused:unused@127.0.0.1/unused'

async def main():
    async with AsyncSessionLocal() as db:
        assert await db.scalar(text('select current_database()')) == 'unused'
        row = (await db.execute(text('''SELECT b.company_id,b.id branch_id,s.id supplier_id,u.id actor_id,
          u2.id approver_id,p.id product_id,l.id location_id
          FROM branches b JOIN suppliers s ON s.company_id=b.company_id
          JOIN users u ON u.company_id=b.company_id JOIN users u2 ON u2.company_id=b.company_id AND u2.id<>u.id
          JOIN products p ON p.company_id=b.company_id JOIN stock_locations l ON l.branch_id=b.id
          WHERE b.deleted_at IS NULL AND s.deleted_at IS NULL AND u.deleted_at IS NULL AND u2.deleted_at IS NULL
          AND p.deleted_at IS NULL AND l.deleted_at IS NULL AND l.is_active=true AND l.company_id=b.company_id LIMIT 1'''))).mappings().first()
        assert row, 'Missing fixture company/branch/two staff/product/location'
        c,b,s,u,a,p,l = [row[k] for k in ['company_id','branch_id','supplier_id','actor_id','approver_id','product_id','location_id']]
    actor = TokenData(user_id=u, company_id=c, branch_id=b, permissions=['*'])
    def po_request():
        return CreatePORequest(supplier_id=s,branch_id=b,order_date=date(2026,10,13),note='isolated clone only',
            items=[POItemCreate(product_id=p,qty_ordered=D(10),unit_cost=D(10),vat_rate=D(0))])
    async def create():
        async with AsyncSessionLocal() as db:
            po = await PurchaseService(db).create_po(c,u,po_request())
            return po.id,po.po_number
    pos = await asyncio.gather(create(),create())
    assert pos[0][1] != pos[1][1]
    po_id,cancel_id = pos[0][0],pos[1][0]
    print('PASS concurrent PO numbering, draft revision capture')
    async with AsyncSessionLocal() as db:
        service=PurchaseService(db)
        await service.update_po(po_id,c,UpdatePORequest(note='revised clone only',revision_reason='แก้หมายเหตุ'),u)
        await service.submit_for_approval(po_id,c,u)
        po=await service.approve_po(po_id,c,a,ApprovePORequest(note='อนุมัติใน clone'))
        po_snapshot=await evidence_for(db,actor,'purchase_order',po)
        assert po_snapshot.payload['source']['approved_by']==str(a)
        assert po_snapshot.payload['source']['note']=='revised clone only'
        try:
            await service.update_po(po_id,c,UpdatePORequest(note='forbidden',revision_reason='no'),u)
        except HTTPException as e: assert e.status_code==409
        else: raise AssertionError('Issued PO editable')
        receipt=await service.receive_goods(c,b,u,CreateGRRequest(po_id=po_id,location_id=l,
            items=[GRItemCreate(po_item_id=po.items[0].id,product_id=p,qty_received=D(1),unit_cost=D(10))]))
        gr_id=receipt.id
        assert (await evidence_for(db,actor,'goods_receipt',receipt)).payload['source']['received_by']==str(u)
        await service.cancel_po(cancel_id,c,u,'ยกเลิกเพื่อทดแทน')
        replaced=await replace_purchase_order(cancel_id,ReplacementRequest(reason='สร้างรุ่นแก้ไข'),actor,db)
        assert replaced['data']['status']=='draft'
        try: await replace_purchase_order(cancel_id,ReplacementRequest(reason='retry'),actor,db)
        except HTTPException as e: assert e.status_code==409
        else: raise AssertionError('Duplicate replacement')
        await db.rollback()
    print('PASS PO approve/snapshot/revision lock; GR capture; cancellation and linked replacement idempotency')

    # Exercise original export contention in separate transactions (real row locking).
    async def original():
        async with AsyncSessionLocal() as db:
            try:
                with patch('app.services.document_archive_service.html_to_pdf_or_html',side_effect=lambda html:(html.encode(),'text/html')):
                    await export_document(db,actor,'purchase_order',po_id,'original')
                return 200
            except HTTPException as e:
                await db.rollback()
                return e.status_code
    assert sorted(await asyncio.gather(original(),original()))==[200,409]
    async with AsyncSessionLocal() as db:
        company=await db.get(Company,c)
        company.name='CHANGED AFTER ISSUANCE'
        await db.commit()
        with patch('app.services.document_archive_service.html_to_pdf_or_html',side_effect=lambda html:(html.encode(),'text/html')):
            result=await export_document(db,actor,'purchase_order',po_id,'copy')
        assert b'CHANGED AFTER ISSUANCE' not in result[0]
        for wrong in [TokenData(user_id=u,company_id=uuid.uuid4(),branch_id=b,permissions=['*']),
                      TokenData(user_id=u,company_id=c,branch_id=uuid.uuid4(),permissions=['*']),
                      TokenData(user_id=u,company_id=c,branch_id=b,permissions=[])]:
            try: await history(db,wrong,'purchase_order',po_id)
            except HTTPException as e: assert e.status_code in [403,404]
            else: raise AssertionError('Scope leak')
        report=await history(db,actor,'purchase_order',po_id)
        assert not report['original_available']
        assert any(e['action']=='draft_revised' and e['reason']=='แก้หมายเหตุ' for e in report['events'])
        counts=await db.scalar(select(func.count(DocumentSnapshot.id)))
        # Evidence failure must roll back receiving quantity, movement and receipt.
        po=await PurchaseService(db).get_po(po_id,c)
        item_id=po.items[0].id
        before_qty=po.items[0].qty_received
        with patch('app.services.purchase_service.capture_gr',AsyncMock(side_effect=RuntimeError('storage unavailable'))):
            try: await PurchaseService(db).receive_goods(c,b,u,CreateGRRequest(po_id=po_id,location_id=l,
                items=[GRItemCreate(po_item_id=item_id,product_id=p,qty_received=D(1),unit_cost=D(10))]))
            except RuntimeError: await db.rollback()
            else: raise AssertionError('Evidence failure accepted')
        po=await PurchaseService(db).get_po(po_id,c)
        assert po.items[0].qty_received==before_qty
        assert await db.scalar(select(func.count(DocumentSnapshot.id)))==counts
    print('PASS original/copy race, frozen company profile, branch/company/permission isolation, atomic GR rollback')

    async with AsyncSessionLocal() as db:
        sale=(await db.execute(text("SELECT id,company_id,branch_id,user_id AS created_by FROM sale_orders WHERE status='completed' LIMIT 1"))).mappings().first()
        assert sale
        tax=ETaxService(db)
        old=(await db.scalars(select(TaxDocument).where(TaxDocument.company_id==sale['company_id'],
            TaxDocument.reference_id==str(sale['id']),TaxDocument.status!='cancelled'))).all()
        for d in old: await tax.cancel_document(d.id,d.company_id,sale['created_by'],CancelDocumentRequest(cancel_reason='clone test only'))
        doc=await tax.issue_tax_invoice(sale['company_id'],sale['branch_id'],sale['created_by'],IssueTaxInvoiceRequest(sale_order_id=sale['id']))
        tax_actor=TokenData(user_id=sale['created_by'],company_id=sale['company_id'],branch_id=sale['branch_id'],permissions=['*'])
        frozen=await evidence_for(db,tax_actor,'sales_tax_document',doc)
        assert frozen.payload['source']['xml_content']==doc.xml_content
        cn=await tax.issue_credit_note(doc.company_id,doc.branch_id,sale['created_by'],IssueCreditNoteRequest(original_document_id=doc.id,reason='clone credit note'))
        assert (await evidence_for(db,tax_actor,'sales_tax_document',cn)).payload['source']['original_document_id']==str(doc.id)
        await tax.cancel_document(doc.id,doc.company_id,sale['created_by'],CancelDocumentRequest(cancel_reason='clone cancellation'))
        hist=await history(db,tax_actor,'sales_tax_document',doc.id)
        assert hist['status']=='cancelled' and not hist['original_available']
        assert {e['action'] for e in hist['events']} >= {'issued','credit_note_linked','cancelled'}
    print('PASS tax snapshot XML, credit-note linkage and cancellation evidence (clone only; no tax submission)')

    async with AsyncSessionLocal() as db:
        inv=await db.scalar(select(SupplierInvoice).where(SupplierInvoice.status=='paid').order_by(SupplierInvoice.created_at.desc()))
        # The preceding AP race regression creates a new invoice snapshot.
        snap=await db.scalar(select(DocumentSnapshot).where(DocumentSnapshot.document_kind=='supplier_invoice',DocumentSnapshot.source_id==inv.id))
        assert snap
        new=await PayableService(db).create_invoice(inv.company_id,inv.created_by,SupplierInvoiceCreate(
            supplier_id=inv.supplier_id,branch_id=inv.branch_id,invoice_date=date(2026,10,13),subtotal=D(100),vat_amount=D(7),wht_amount=D(0)))
        await PayableService(db).cancel_invoice(new.id,new.company_id,new.created_by,'clone invoice reversal')
        assert await db.scalar(select(DocumentEvent.id).where(DocumentEvent.source_id==new.id,DocumentEvent.action=='cancelled'))
        snapshots=(await db.scalars(select(DocumentSnapshot))).all()
        assert {s.document_kind for s in snapshots}=={'purchase_order','goods_receipt','supplier_invoice','payment_voucher','wht_certificate','sales_tax_document'}
        assert all(snapshot_digest(s)==s.content_sha256 for s in snapshots)
        for kind in {s.document_kind for s in snapshots}:
            snapshot=next(s for s in snapshots if s.document_kind==kind)
            content,media=html_to_pdf_or_html(snapshot.rendered_html)
            assert media=='application/pdf' and content.startswith(b'%PDF'),kind
        for table in ['document_snapshots','document_events']:
            for statement in [f'UPDATE {table} SET id=id',f'DELETE FROM {table}',f'TRUNCATE {table}']:
                try:
                    async with db.begin_nested(): await db.execute(text(statement))
                except DBAPIError as e: assert 'append-only' in str(e)
                else: raise AssertionError('Archive mutation allowed')
    print('PASS all six snapshot kinds, six PDFs, invoice reversal reason, checksum and append-only triggers')
    await engine.dispose()

asyncio.run(main())
