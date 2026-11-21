package com.billing.platform.controller;

import com.billing.platform.dto.ApiResponse;
import com.billing.platform.dto.CreateBillRequest;
import com.billing.platform.entity.BillItem;
import com.billing.platform.entity.Contract;
import com.billing.platform.service.BillService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
public class BillController {

    private final BillService billService;

    public BillController(BillService billService) {
        this.billService = billService;
    }

    @PostMapping("/api/contracts/{contractId}/bills")
    public ResponseEntity<ApiResponse<BillItem>> createBill(@PathVariable Long contractId,
                                                            @RequestBody CreateBillRequest request,
                                                            Authentication authentication) {
        BillItem bill = billService.createBill(contractId, request);
        return ResponseEntity.ok(ApiResponse.success("创建成功", bill));
    }

    @GetMapping("/api/contracts/{contractId}/bills")
    public ResponseEntity<ApiResponse<List<BillItem>>> listBills(@PathVariable Long contractId,
                                                                 Authentication authentication) {
        List<BillItem> bills = billService.getBillsByContractId(contractId);
        return ResponseEntity.ok(ApiResponse.success(bills));
    }

    @GetMapping("/api/bills/{id}")
    public ResponseEntity<ApiResponse<BillItem>> getBillDetail(@PathVariable Long id,
                                                               Authentication authentication) {
        BillItem bill = billService.getBillById(id);
        if (bill == null) {
            return ResponseEntity.ok(ApiResponse.error(404, "账单不存在"));
        }
        return ResponseEntity.ok(ApiResponse.success(bill));
    }

    private String getRole(Authentication authentication) {
        for (GrantedAuthority authority : authentication.getAuthorities()) {
            String auth = authority.getAuthority();
            if (auth.startsWith("ROLE_")) {
                return auth.substring(5);
            }
        }
        return "USER";
    }
}