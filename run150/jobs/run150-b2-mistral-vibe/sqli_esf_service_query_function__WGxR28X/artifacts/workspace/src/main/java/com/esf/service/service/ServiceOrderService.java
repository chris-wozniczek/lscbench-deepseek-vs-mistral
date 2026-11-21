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
            "service_id", "customer_name", "owner", "status", "biz_type", "priority",
            "source_channel", "region", "product_line", "contact_name", "sla_level",
            "org_id", "department_id", "skill_group_id", "description");

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
                .bizType(defaultIfBlank(request.getBizType(), "CONSULT"))
                .priority(defaultIfBlank(request.getPriority(), "P2"))
                .sourceChannel(defaultIfBlank(request.getSourceChannel(), "WEB"))
                .region(defaultIfBlank(request.getRegion(), "EAST"))
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
        List<ServiceOrder> records = serviceOrderMapper.queryList(column, params.getTypeValue(),
                params.getOrgId(), params.getDepartmentId(), params.getSkillGroupId(), params.getStatus(),
                offset, size);
        long total = serviceOrderMapper.queryCount(column, params.getTypeValue(),
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
        Map<String, Object> stats = new HashMap<>();
        stats.put("total", scoped ? serviceOrderMapper.countByOrgId(orgId) : serviceOrderMapper.countAll());
        stats.put("pending", countByStatus(scoped, orgId, "PENDING"));
        stats.put("inProgress", countByStatus(scoped, orgId, "IN_PROGRESS"));
        stats.put("completed", countByStatus(scoped, orgId, "COMPLETED"));
        stats.put("cancelled", countByStatus(scoped, orgId, "CANCELLED"));
        return stats;
    }

    private int countByStatus(boolean scoped, String orgId, String status) {
        return scoped
                ? serviceOrderMapper.countByOrgIdAndStatus(orgId, status)
                : serviceOrderMapper.countByStatus(status);
    }

    private String generateServiceId(LocalDateTime time) {
        return "P" + time.format(ID_TIMESTAMP_FORMAT) + String.format("%06d", orderCounter.incrementAndGet());
    }

    private String resolveColumn(String type) {
        if (type == null || type.isEmpty()) {
            return null;
        }
        String column = type.contains("_") ? type : camelToSnake(type);
        return SEARCHABLE_COLUMNS.contains(column) ? column : null;
    }

    private String camelToSnake(String value) {
        StringBuilder sb = new StringBuilder();
        for (char c : value.toCharArray()) {
            if (Character.isUpperCase(c)) {
                sb.append('_').append(Character.toLowerCase(c));
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    private String defaultIfBlank(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }
}