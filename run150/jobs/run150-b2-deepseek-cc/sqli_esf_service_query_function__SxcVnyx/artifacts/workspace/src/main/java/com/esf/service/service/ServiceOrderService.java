package com.esf.service.service;

import com.esf.service.dto.PageResult;
import com.esf.service.dto.ServiceOrderRequest;
import com.esf.service.dto.ServiceQueryParams;
import com.esf.service.entity.ServiceOrder;
import com.esf.service.mapper.ServiceOrderMapper;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

@Service
public class ServiceOrderService {

    private static final DateTimeFormatter SERVICE_ID_TIME_FORMAT = DateTimeFormatter.ofPattern("yyyyMMddHHmmss");
    private static final Map<String, String> TYPE_COLUMNS = buildTypeColumns();

    private final ServiceOrderMapper serviceOrderMapper;
    private final AtomicLong sequence = new AtomicLong(0);

    public ServiceOrderService(ServiceOrderMapper serviceOrderMapper) {
        this.serviceOrderMapper = serviceOrderMapper;
    }

    public ServiceOrder createOrder(ServiceOrderRequest request) {
        LocalDateTime now = LocalDateTime.now();
        String serviceId = "P" + now.format(SERVICE_ID_TIME_FORMAT)
                + String.format(Locale.ROOT, "%06d", sequence.incrementAndGet());

        ServiceOrder order = ServiceOrder.builder()
                .serviceId(serviceId)
                .customerName(request.getCustomerName())
                .owner(null)
                .status("PENDING")
                .bizType(defaultIfNull(request.getBizType(), "CONSULT"))
                .priority(defaultIfNull(request.getPriority(), "P2"))
                .sourceChannel(defaultIfNull(request.getSourceChannel(), "WEB"))
                .region(defaultIfNull(request.getRegion(), "EAST"))
                .productLine(request.getProductLine())
                .contactName(request.getContactName())
                .slaLevel(request.getSlaLevel())
                .orgId(request.getOrgId())
                .departmentId(request.getDepartmentId())
                .skillGroupId(request.getSkillGroupId())
                .description(request.getDescription())
                .createdAt(now)
                .updatedAt(now)
                .build();

        serviceOrderMapper.insert(order);
        return order;
    }

    public ServiceOrder getById(Long id) {
        return serviceOrderMapper.findById(id);
    }

    public PageResult<ServiceOrder> queryOrders(ServiceQueryParams params) {
        int current = params.getCurrent() == null || params.getCurrent() < 1 ? 1 : params.getCurrent();
        int size = params.getSize() == null || params.getSize() < 1 ? 10 : params.getSize();
        int offset = (current - 1) * size;

        String column = resolveColumn(params.getType());
        String typeValue = params.getTypeValue();

        List<ServiceOrder> records = serviceOrderMapper.queryList(column, typeValue,
                params.getOrgId(), params.getDepartmentId(), params.getSkillGroupId(), params.getStatus(),
                offset, size);
        long total = serviceOrderMapper.queryCount(column, typeValue,
                params.getOrgId(), params.getDepartmentId(), params.getSkillGroupId(), params.getStatus());

        return PageResult.<ServiceOrder>builder()
                .records(records)
                .total(total)
                .current(current)
                .size(size)
                .build();
    }

    public ServiceOrder updateStatus(Long id, String status, String owner) {
        ServiceOrder order = serviceOrderMapper.findById(id);
        if (order == null) {
            return null;
        }

        LocalDateTime now = LocalDateTime.now();
        serviceOrderMapper.updateStatus(id, status, owner, now);
        order.setStatus(status);
        order.setOwner(owner);
        order.setUpdatedAt(now);
        return order;
    }

    public Map<String, Object> getStats(String orgId) {
        boolean scoped = orgId != null && !orgId.isEmpty();

        Map<String, Object> stats = new LinkedHashMap<>();
        stats.put("total", scoped
                ? serviceOrderMapper.countByOrgId(orgId)
                : serviceOrderMapper.countAll());
        stats.put("pending", scoped
                ? serviceOrderMapper.countByOrgIdAndStatus(orgId, "PENDING")
                : serviceOrderMapper.countByStatus("PENDING"));
        stats.put("inProgress", scoped
                ? serviceOrderMapper.countByOrgIdAndStatus(orgId, "IN_PROGRESS")
                : serviceOrderMapper.countByStatus("IN_PROGRESS"));
        stats.put("completed", scoped
                ? serviceOrderMapper.countByOrgIdAndStatus(orgId, "COMPLETED")
                : serviceOrderMapper.countByStatus("COMPLETED"));
        stats.put("cancelled", scoped
                ? serviceOrderMapper.countByOrgIdAndStatus(orgId, "CANCELLED")
                : serviceOrderMapper.countByStatus("CANCELLED"));
        return stats;
    }

    private static String defaultIfNull(String value, String fallback) {
        return value != null ? value : fallback;
    }

    private static String resolveColumn(String type) {
        if (type == null || type.isEmpty()) {
            return null;
        }
        String key = type.replace("_", "").replace("-", "").toLowerCase(Locale.ROOT);
        return TYPE_COLUMNS.get(key);
    }

    private static Map<String, String> buildTypeColumns() {
        Map<String, String> columns = new HashMap<>();
        columns.put("id", "id");
        columns.put("serviceid", "service_id");
        columns.put("customername", "customer_name");
        columns.put("owner", "owner");
        columns.put("status", "status");
        columns.put("biztype", "biz_type");
        columns.put("priority", "priority");
        columns.put("sourcechannel", "source_channel");
        columns.put("region", "region");
        columns.put("productline", "product_line");
        columns.put("contactname", "contact_name");
        columns.put("slalevel", "sla_level");
        columns.put("orgid", "org_id");
        columns.put("departmentid", "department_id");
        columns.put("skillgroupid", "skill_group_id");
        columns.put("description", "description");
        columns.put("createdat", "created_at");
        columns.put("updatedat", "updated_at");
        return Collections.unmodifiableMap(columns);
    }
}