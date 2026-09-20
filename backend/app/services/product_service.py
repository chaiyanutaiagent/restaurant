from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import (
    Category,
    PriceList,
    PriceListItem,
    Product,
    ProductImage,
    ProductVariant,
    Unit,
)
from app.models.branch import Branch
from app.models.crm import Customer
from app.models.restaurant import Brand
from app.schemas.product import (
    CategoryCreate,
    CategoryUpdate,
    PriceListCreate,
    PriceListItemCreate,
    ProductCreate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
    UnitCreate,
    UnitUpdate,
)


class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_units(self, company_id: uuid.UUID) -> list[Unit]:
        rows = await self.db.scalars(
            select(Unit)
            .where(Unit.company_id == company_id, Unit.deleted_at.is_(None))
            .order_by(Unit.code.asc())
        )
        return rows.all()

    async def create_unit(self, company_id: uuid.UUID, data: UnitCreate) -> Unit:
        await self._ensure_unit_code_available(company_id, data.code)
        unit = Unit(company_id=company_id, **data.model_dump())
        self.db.add(unit)
        await self.db.commit()
        await self.db.refresh(unit)
        return unit

    async def update_unit(self, unit_id: uuid.UUID, company_id: uuid.UUID, data: UnitUpdate) -> Unit:
        unit = await self._get_unit(unit_id, company_id)
        payload = data.model_dump(exclude_unset=True)
        if "code" in payload and payload["code"] != unit.code:
            await self._ensure_unit_code_available(company_id, payload["code"], exclude_id=unit.id)
        for key, value in payload.items():
            setattr(unit, key, value)
        await self.db.commit()
        await self.db.refresh(unit)
        return unit

    async def delete_unit(self, unit_id: uuid.UUID, company_id: uuid.UUID) -> None:
        unit = await self._get_unit(unit_id, company_id)
        unit.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def list_categories(self, company_id: uuid.UUID, tree: bool = False) -> list[Category]:
        rows = await self.db.scalars(
            select(Category)
            .where(Category.company_id == company_id, Category.deleted_at.is_(None))
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
        categories = rows.all()
        if not tree:
            return categories

        by_parent: dict[uuid.UUID | None, list[Category]] = defaultdict(list)
        for category in categories:
            category.children = []
            by_parent[category.parent_id].append(category)
        for category in categories:
            category.children = by_parent.get(category.id, [])
        return by_parent.get(None, [])

    async def create_category(self, company_id: uuid.UUID, data: CategoryCreate) -> Category:
        payload = data.model_dump()
        code = payload.get("code")
        if code:
            await self._ensure_category_code_available(company_id, code)
        category = Category(company_id=company_id, **payload)
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def update_category(self, cat_id: uuid.UUID, company_id: uuid.UUID, data: CategoryUpdate) -> Category:
        category = await self._get_category(cat_id, company_id)
        payload = data.model_dump(exclude_unset=True)
        code = payload.get("code")
        if code and code != category.code:
            await self._ensure_category_code_available(company_id, code, exclude_id=category.id)
        for key, value in payload.items():
            setattr(category, key, value)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def delete_category(self, cat_id: uuid.UUID, company_id: uuid.UUID) -> None:
        category = await self._get_category(cat_id, company_id)
        active_products = await self.db.scalar(
            select(func.count(Product.id)).where(
                Product.company_id == company_id,
                Product.category_id == category.id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        if active_products:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category has active products",
            )
        category.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def list_products(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        product_type: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Product], int]:
        filters = [Product.company_id == company_id, Product.deleted_at.is_(None)]
        if category_id:
            filters.append(Product.category_id == category_id)
        if product_type:
            filters.append(Product.product_type == product_type)
        if is_active is not None:
            filters.append(Product.is_active.is_(is_active))
        if search:
            like = f"%{search.strip()}%"
            filters.append(
                or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode.ilike(like))
            )

        total = await self.db.scalar(select(func.count(Product.id)).where(*filters)) or 0
        statement = (
            select(Product)
            .where(*filters)
            .options(selectinload(Product.variants), selectinload(Product.unit))
            .order_by(Product.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = await self.db.scalars(statement)
        return rows.all(), int(total)

    async def get_product(self, product_id: uuid.UUID, company_id: uuid.UUID) -> Product:
        statement = (
            select(Product)
            .where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
            )
            .options(
                selectinload(Product.category),
                selectinload(Product.unit),
                selectinload(Product.variants),
                selectinload(Product.images),
            )
        )
        product = await self.db.scalar(statement)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        product.variants = [variant for variant in product.variants if variant.deleted_at is None]
        return product

    async def create_product(self, company_id: uuid.UUID, data: ProductCreate) -> Product:
        await self._ensure_product_sku_available(company_id, data.sku)
        product = Product(company_id=company_id, **data.model_dump())
        self.db.add(product)
        await self.db.commit()
        return await self.get_product(product.id, company_id)

    async def update_product(self, product_id: uuid.UUID, company_id: uuid.UUID, data: ProductUpdate) -> Product:
        product = await self._get_product_entity(product_id, company_id)
        payload = data.model_dump(exclude_unset=True)
        if "sku" in payload and payload["sku"] != product.sku:
            await self._ensure_product_sku_available(company_id, payload["sku"], exclude_id=product.id)
        for key, value in payload.items():
            setattr(product, key, value)
        await self.db.commit()
        return await self.get_product(product.id, company_id)

    async def delete_product(self, product_id: uuid.UUID, company_id: uuid.UUID) -> None:
        product = await self._get_product_entity(product_id, company_id)
        deleted_at = datetime.now(timezone.utc)
        product.deleted_at = deleted_at
        for variant in await self._list_product_variants(product.id, company_id):
            variant.deleted_at = deleted_at
        await self.db.commit()

    async def add_product_image(
        self,
        product_id: uuid.UUID,
        company_id: uuid.UUID,
        url: str,
        filename: str,
        is_primary: bool = True,
    ) -> ProductImage:
        product = await self._get_product_entity(product_id, company_id)
        if is_primary:
            await self._clear_primary_images(product.id, company_id)
        next_sort = await self.db.scalar(
            select(func.coalesce(func.max(ProductImage.sort_order), 0) + 1).where(
                ProductImage.product_id == product.id,
                ProductImage.company_id == company_id,
            )
        )
        image = ProductImage(
            product_id=product.id,
            company_id=company_id,
            url=url,
            filename=filename,
            is_primary=is_primary,
            sort_order=int(next_sort or 1),
        )
        self.db.add(image)
        if is_primary or not product.image_url:
            product.image_url = url
        await self.db.commit()
        await self.db.refresh(image)
        return image

    async def delete_product_image(self, product_id: uuid.UUID, image_id: uuid.UUID, company_id: uuid.UUID) -> ProductImage:
        product = await self._get_product_entity(product_id, company_id)
        image = await self.db.scalar(
            select(ProductImage).where(
                ProductImage.id == image_id,
                ProductImage.product_id == product.id,
                ProductImage.company_id == company_id,
            )
        )
        if image is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
        was_primary = image.is_primary
        await self.db.delete(image)
        await self.db.flush()
        if was_primary:
            next_image = await self.db.scalar(
                select(ProductImage)
                .where(
                    ProductImage.product_id == product.id,
                    ProductImage.company_id == company_id,
                )
                .order_by(ProductImage.sort_order.asc(), ProductImage.created_at.asc())
            )
            product.image_url = next_image.url if next_image else None
            if next_image:
                next_image.is_primary = True
        await self.db.commit()
        return image

    async def set_primary_image(self, product_id: uuid.UUID, image_id: uuid.UUID, company_id: uuid.UUID) -> None:
        product = await self._get_product_entity(product_id, company_id)
        image = await self.db.scalar(
            select(ProductImage).where(
                ProductImage.id == image_id,
                ProductImage.product_id == product.id,
                ProductImage.company_id == company_id,
            )
        )
        if image is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
        await self._clear_primary_images(product.id, company_id)
        image.is_primary = True
        product.image_url = image.url
        await self.db.commit()

    async def add_variant(
        self,
        product_id: uuid.UUID,
        company_id: uuid.UUID,
        data: ProductVariantCreate,
    ) -> ProductVariant:
        product = await self._get_product_entity(product_id, company_id)
        await self._ensure_product_sku_available(company_id, data.sku)
        variant = ProductVariant(company_id=company_id, product_id=product.id, **data.model_dump(exclude={"product_id"}))
        self.db.add(variant)
        await self.db.commit()
        await self.db.refresh(variant)
        return variant

    async def update_variant(self, variant_id: uuid.UUID, company_id: uuid.UUID, data: ProductVariantUpdate) -> ProductVariant:
        variant = await self._get_variant(variant_id, company_id)
        payload = data.model_dump(exclude_unset=True)
        if "sku" in payload and payload["sku"] != variant.sku:
            await self._ensure_product_sku_available(company_id, payload["sku"], exclude_variant_id=variant.id)
        for key, value in payload.items():
            setattr(variant, key, value)
        await self.db.commit()
        await self.db.refresh(variant)
        return variant

    async def delete_variant(self, variant_id: uuid.UUID, company_id: uuid.UUID) -> None:
        variant = await self._get_variant(variant_id, company_id)
        variant.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def list_price_lists(self, company_id: uuid.UUID) -> list[PriceList]:
        rows = await self.db.scalars(
            select(PriceList)
            .where(PriceList.company_id == company_id, PriceList.deleted_at.is_(None))
            .order_by(PriceList.is_default.desc(), PriceList.name.asc())
        )
        return rows.all()

    async def create_price_list(self, company_id: uuid.UUID, data: PriceListCreate) -> PriceList:
        for model, entity_id, label in (
            (Brand, data.brand_id, "Brand"),
            (Branch, data.branch_id, "Branch"),
            (Customer, data.customer_id, "Customer"),
        ):
            if entity_id is None:
                continue
            entity = await self.db.scalar(
                select(model.id).where(
                    model.id == entity_id,
                    model.company_id == company_id,
                    model.deleted_at.is_(None),
                )
            )
            if entity is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{label} does not belong to the active Company",
                )
        if data.is_default:
            await self._unset_default_price_lists(company_id)
        price_list = PriceList(company_id=company_id, **data.model_dump())
        self.db.add(price_list)
        await self.db.commit()
        await self.db.refresh(price_list)
        return price_list

    async def set_price(self, company_id: uuid.UUID, data: PriceListItemCreate) -> PriceListItem:
        await self._get_product_entity(data.product_id, company_id)
        statement: Select[tuple[PriceListItem]] = select(PriceListItem).where(
            PriceListItem.company_id == company_id,
            PriceListItem.price_list_id == data.price_list_id,
            PriceListItem.product_id == data.product_id,
        )
        if data.variant_id is None:
            statement = statement.where(PriceListItem.variant_id.is_(None))
        else:
            statement = statement.where(PriceListItem.variant_id == data.variant_id)
        item = await self.db.scalar(statement)
        if item is None:
            item = PriceListItem(company_id=company_id, **data.model_dump())
            self.db.add(item)
        else:
            item.price = data.price
            item.min_qty = data.min_qty
        price_list = await self.db.scalar(
            select(PriceList)
            .where(
                PriceList.id == data.price_list_id,
                PriceList.company_id == company_id,
                PriceList.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if price_list is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price list not found")
        price_list.version = int(price_list.version or 1) + 1
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def get_product_price(
        self,
        product_id: uuid.UUID,
        company_id: uuid.UUID,
        price_list_id: uuid.UUID | None = None,
        variant_id: uuid.UUID | None = None,
        qty: Decimal = Decimal("1"),
    ) -> Decimal:
        product = await self._get_product_entity(product_id, company_id)
        resolved_price_list_id = price_list_id
        if resolved_price_list_id is None:
            resolved_price_list_id = await self.db.scalar(
                select(PriceList.id).where(
                    PriceList.company_id == company_id,
                    PriceList.deleted_at.is_(None),
                    PriceList.is_default.is_(True),
                    PriceList.is_active.is_(True),
                )
            )
        if resolved_price_list_id:
            statement = (
                select(PriceListItem)
                .where(
                    PriceListItem.company_id == company_id,
                    PriceListItem.price_list_id == resolved_price_list_id,
                    PriceListItem.product_id == product_id,
                    PriceListItem.min_qty <= qty,
                )
                .order_by(PriceListItem.min_qty.desc())
            )
            if variant_id is None:
                statement = statement.where(PriceListItem.variant_id.is_(None))
            else:
                statement = statement.where(PriceListItem.variant_id == variant_id)
            item = await self.db.scalar(statement)
            if item is not None:
                return item.price
        if variant_id is not None:
            variant = await self._get_variant(variant_id, company_id)
            if variant.selling_price is not None:
                return variant.selling_price
        return product.selling_price

    async def _get_unit(self, unit_id: uuid.UUID, company_id: uuid.UUID) -> Unit:
        unit = await self.db.scalar(
            select(Unit).where(Unit.id == unit_id, Unit.company_id == company_id, Unit.deleted_at.is_(None))
        )
        if unit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
        return unit

    async def _get_category(self, cat_id: uuid.UUID, company_id: uuid.UUID) -> Category:
        category = await self.db.scalar(
            select(Category).where(
                Category.id == cat_id,
                Category.company_id == company_id,
                Category.deleted_at.is_(None),
            )
        )
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return category

    async def _get_product_entity(self, product_id: uuid.UUID, company_id: uuid.UUID) -> Product:
        product = await self.db.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
            )
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return product

    async def _get_variant(self, variant_id: uuid.UUID, company_id: uuid.UUID) -> ProductVariant:
        variant = await self.db.scalar(
            select(ProductVariant).where(
                ProductVariant.id == variant_id,
                ProductVariant.company_id == company_id,
                ProductVariant.deleted_at.is_(None),
            )
        )
        if variant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
        return variant

    async def _list_product_variants(self, product_id: uuid.UUID, company_id: uuid.UUID) -> list[ProductVariant]:
        rows = await self.db.scalars(
            select(ProductVariant).where(
                ProductVariant.product_id == product_id,
                ProductVariant.company_id == company_id,
                ProductVariant.deleted_at.is_(None),
            )
        )
        return rows.all()

    async def _ensure_unit_code_available(self, company_id: uuid.UUID, code: str, exclude_id: uuid.UUID | None = None) -> None:
        statement = select(Unit.id).where(
            Unit.company_id == company_id,
            Unit.code == code,
            Unit.deleted_at.is_(None),
        )
        if exclude_id:
            statement = statement.where(Unit.id != exclude_id)
        existing = await self.db.scalar(statement)
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unit code already exists")

    async def _ensure_category_code_available(
        self,
        company_id: uuid.UUID,
        code: str,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        statement = select(Category.id).where(
            Category.company_id == company_id,
            Category.code == code,
            Category.deleted_at.is_(None),
        )
        if exclude_id:
            statement = statement.where(Category.id != exclude_id)
        existing = await self.db.scalar(statement)
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category code already exists")

    async def _ensure_product_sku_available(
        self,
        company_id: uuid.UUID,
        sku: str,
        exclude_id: uuid.UUID | None = None,
        exclude_variant_id: uuid.UUID | None = None,
    ) -> None:
        product_statement = select(Product.id).where(
            Product.company_id == company_id,
            Product.sku == sku,
            Product.deleted_at.is_(None),
        )
        if exclude_id:
            product_statement = product_statement.where(Product.id != exclude_id)
        product_exists = await self.db.scalar(product_statement)
        if product_exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SKU already exists")

        variant_statement = select(ProductVariant.id).where(
            ProductVariant.company_id == company_id,
            ProductVariant.sku == sku,
            ProductVariant.deleted_at.is_(None),
        )
        if exclude_variant_id:
            variant_statement = variant_statement.where(ProductVariant.id != exclude_variant_id)
        variant_exists = await self.db.scalar(variant_statement)
        if variant_exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SKU already exists")

    async def _clear_primary_images(self, product_id: uuid.UUID, company_id: uuid.UUID) -> None:
        await self.db.execute(
            update(ProductImage)
            .where(ProductImage.product_id == product_id, ProductImage.company_id == company_id)
            .values(is_primary=False)
        )

    async def _unset_default_price_lists(self, company_id: uuid.UUID) -> None:
        await self.db.execute(
            update(PriceList)
            .where(PriceList.company_id == company_id, PriceList.deleted_at.is_(None))
            .values(is_default=False)
        )
