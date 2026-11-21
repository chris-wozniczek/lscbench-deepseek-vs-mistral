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

    private static final DateTimeFormatter ID_TIMESTAMP_FORMAT = DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private static final Set<String> SEARCHABLE_COLUMNS = Set.of(
            "id", "service_id", "customer_name", "owner", "status", "biz_type",
            "priority", "source_channel", "region", "product_line", "contact_name",
            "sla_level", "org_id", "department_id", "skill_group_id", "description",
            "created_at", "updated_at");

    private final ServiceOrderMapper serviceOrderMapper;
    private final AtomicLong orderCounter = new AtomicLong(0);

    public ServiceOrderService(ServiceOrderMapper serviceOrderMapper) {
        this.serviceOrderMapper = serviceOrderMapper;
    }

    public ServiceOrder createOrder(ServiceOrderRequest request) {
        LocalDateTime now = LocalDateTime.now();
        ServiceOrder order = ServiceOrder.builder()
                .serviceId(generateServiceId(now))
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
        int current = params.getCurrent() == null ? 1 : params.getCurrent();
        int size = params.getSize() == null ? 10 : params.getSize();
        int offset = (current - 1) * size;

        String column = resolveColumn(params.getType());
        String typeValue = params.getTypeValue();
        String orgId = params.getOrgId();
        String departmentId = params.getDepartmentId();
        String skillGroupId = params.getSkillGroupId();
        String status = params.getStatus();

        List<ServiceOrder> records = serviceOrderMapper.queryList(
                column, typeValue, orgId, departmentId, skillGroupId, status, offset, size);
        long total = serviceOrderMapper.queryCount(
                column, typeValue, orgId, departmentId, skillGroupId, status);

        return PageResult.<ServiceOrder>builder()
                .records(records)
                .total(total)
                .current(current)
                .size(size)
                .build();
    }

    public ServiceOrder updateStatus(Long id, String status, String owner) {
        ServiceOrder existing = serviceOrderMapper.findById(id);
        if (existing == null) {
            return null;
        }
        LocalDateTime now = LocalDateTime.now();
        serviceOrderMapper.updateStatus(id, status, owner, now);
        existing.setStatus(status);
        existing.setOwner(owner);
        existing.setUpdatedAt(now);
        return existing;
    }

    public Map<String, Object> getStats(String orgId) {
        Map<String, Object> stats = new HashMap<>();
        if (orgId != null && !orgId.isEmpty()) {
            stats.put("total", serviceOrderMapper.countByOrgId(orgId));
            stats.put("pending", serviceOrderMapper.countByOrgIdAndStatus(orgId, "PENDING"));
            stats.put("inProgress", serviceOrderMapper.countByOrgIdAndStatus(orgId, "IN_PROGRESS"));
            stats.put("completed", serviceOrderMapper.countByOrgIdAndStatus(orgId, "COMPLETED"));
            stats.put("cancelled", serviceOrderMapper.countByOrgIdAndStatus(orgId, "CANCELLED"));
        } else {
            stats.put("total", serviceOrderMapper.countAll());
            stats.put("pending", serviceOrderMapper.countByStatus("PENDING"));
            stats.put("inProgress", serviceOrderMapper.countByStatus("IN_PROGRESS"));
            stats.put("completed", serviceOrderMapper.countByStatus("COMPLETED"));
            stats.put("cancelled", serviceOrderMapper.countByStatus("CANCELLED"));
        }
        return stats;
    }

    private String generateServiceId(LocalDateTime time) {
        return "P" + time.format(ID_TIMESTAMP_FORMAT) + String.format("%06d", orderCounter.incrementAndGet());
    }

    private String resolveColumn(String type) {
        if (type == null || type.isEmpty()) {
            return null;
        }
        String column = type.replaceAll("([a-z0-9])([A-Z])", "$1_$2").toLowerCase();
        return SEARCHABLE_COLUMNS.contains(column) ? column : null;
    }

    private static String defaultIfNull(String value, String defaultValue) {
        return value == null ? defaultValue : value;
    }
}