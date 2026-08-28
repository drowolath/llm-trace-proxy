from fastapi import Header, HTTPException, status


async def get_tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID")) -> str:
    """Extract the caller's tenant identifier from the X-Tenant-ID header.

    The header is mandatory: it is what lets the proxy attribute cost and
    usage to a specific caller without any change to that caller's code.
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header: X-Tenant-ID",
        )
    return x_tenant_id
