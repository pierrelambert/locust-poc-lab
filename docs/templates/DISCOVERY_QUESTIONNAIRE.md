# Pre-POC Discovery Questionnaire

**Customer:** `{{ customer_name }}`  
**SA owner:** `{{ sa_name }}`  
**Date completed:** `{{ date }}`

---

Use this questionnaire during the initial discovery call to capture the context needed to scope a meaningful POC. Answers feed directly into the [POC Charter](POC_CHARTER_TEMPLATE.md).

---

## 1. Business Context

1. **What business initiative or project is driving this evaluation?**  
   `{{ answer }}`

2. **What is the timeline for a production decision?**  
   `{{ answer }}`

3. **Who are the key stakeholders and what does the approval chain look like?**  
   `{{ answer }}`

4. **Has the customer evaluated Redis (Enterprise or OSS) before? If so, what was the outcome?**  
   `{{ answer }}`

## 2. Current Architecture

5. **What data store(s) are in use today for the workload in question?**  
   `{{ answer }}`

6. **What is the deployment model — VMs, Kubernetes, managed service, or hybrid?**  
   `{{ answer }}`

7. **What cloud provider(s) and region(s) are involved?**  
   `{{ answer }}`

8. **What is the current topology — standalone, sentinel, cluster, or other?**  
   `{{ answer }}`

## 3. Workload Profile

9. **Describe the primary workload — caching, session store, real-time analytics, messaging, or other?**  
   `{{ answer }}`

10. **What is the approximate read/write ratio?**  
    `{{ answer }}`

11. **What are the expected throughput requirements (operations per second)?**  
    `{{ answer }}`

12. **What are the latency expectations — average and tail (p99)?**  
    `{{ answer }}`

## 4. Resiliency and Operations

13. **What is the current RTO (recovery time objective) for this workload?**  
    `{{ answer }}`

14. **How are failovers handled today — automatic, manual, or not tested?**  
    `{{ answer }}`

15. **What does the current upgrade or maintenance process look like? How much downtime is involved?**  
    `{{ answer }}`

16. **How many people are involved in operating the data layer today?**  
    `{{ answer }}`

## 5. Success Criteria and Risks

17. **What would make this POC a clear success in the customer's eyes?**  
    `{{ answer }}`

18. **What would make it a failure or a reason to walk away?**  
    `{{ answer }}`

19. **Are there any known constraints — security, compliance, network, or procurement?**  
    `{{ answer }}`

20. **What competing solutions or approaches is the customer also considering?**  
    `{{ answer }}`

---

## Notes

`{{ additional context, follow-up items, or observations from the discovery call }}`

