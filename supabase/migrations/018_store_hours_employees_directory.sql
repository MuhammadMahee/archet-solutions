create table public.store_hours_directory (
  dealer text not null,
  store_id text not null,
  market text not null,
  store text not null,
  company text not null,
  carrier text not null,
  source_id text,
  schedules jsonb not null,
  updated_at timestamptz not null default now(),
  primary key(dealer,store_id)
);
create table public.store_hours_uploads (
  id uuid primary key default gen_random_uuid(),
  filename text not null,
  rows jsonb not null,
  uploaded_by uuid not null references public.portal_users(id),
  uploaded_at timestamptz not null default now(),
  applied_at timestamptz
);
create table public.store_hours_manual_employees (
  dealer text not null,
  store_id text not null,
  report_date date not null,
  employee_key text not null,
  employee text not null,
  created_by uuid not null references public.portal_users(id),
  created_at timestamptz not null default now(),
  primary key(dealer,store_id,report_date,employee_key)
);
-- Keep the legacy store/day table compatible with the running deployment.
create table public.store_hours_employee_reviews (
  dealer text not null,
  store_id text not null,
  report_date date not null,
  employee_key text not null,
  opening_time time,
  closing_time time,
  camera_in time,
  camera_out time,
  revision integer not null default 1,
  updated_by uuid not null references public.portal_users(id),
  updated_at timestamptz not null default now(),
  primary key(dealer,store_id,report_date,employee_key)
);
alter table public.store_hours_employee_reviews enable row level security;
revoke all on public.store_hours_employee_reviews from public,anon,authenticated;
grant all on public.store_hours_employee_reviews to service_role;
alter table public.store_hours_directory enable row level security;
alter table public.store_hours_uploads enable row level security;
alter table public.store_hours_manual_employees enable row level security;
revoke all on public.store_hours_directory,public.store_hours_uploads,public.store_hours_manual_employees from public,anon,authenticated;
grant all on public.store_hours_directory,public.store_hours_uploads,public.store_hours_manual_employees to service_role;

-- Seed all 38 workbook stores, including the 11 previously outside the Calling Tree.
insert into public.store_hours_directory(dealer,store_id,market,store,company,carrier,source_id,schedules)
select dealer,store_id,market,store,company,carrier,source_id,schedules
from jsonb_to_recordset($schedules$
[
  {
    "dealer": "SRH",
    "store_id": "TXD2121A",
    "market": "DALLAS",
    "store": "GILMER",
    "company": "SUPREME",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "srh",
    "schedules": {
      "weekday": {
        "opening_time": "09:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "09:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "SRH",
    "store_id": "TXD510A",
    "market": "DALLAS",
    "store": "LOOP",
    "company": "SUPREME",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "srh",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "SRH",
    "store_id": "TXLS222A",
    "market": "LOUISANA",
    "store": "LA EEND",
    "company": "SUPREME",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "srh",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "SRH",
    "store_id": "TXLS835A",
    "market": "LOUISANA",
    "store": "LA BENTON",
    "company": "SUPREME",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "srh",
    "schedules": {
      "weekday": {
        "opening_time": "09:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "09:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "ARM",
    "store_id": "317-002",
    "market": "CHICAGO",
    "store": "LEE ST",
    "company": "TALKALOT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "arm2",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "AMQ",
    "store_id": "N1310C",
    "market": "CHICAGO",
    "store": "MT PROSPECT",
    "company": "ARM WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "arm1",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "AMQ",
    "store_id": "N1329B",
    "market": "CHICAGO",
    "store": "GLENVIEW",
    "company": "ARM WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "arm1",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "18:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "AMQ",
    "store_id": "N1311B",
    "market": "CHICAGO",
    "store": "WEST CHICAGO",
    "company": "ARM WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "arm1",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "AMQ",
    "store_id": "N1301A",
    "market": "CHICAGO",
    "store": "BLUE ISLAND",
    "company": "ARM WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "arm1",
    "schedules": {
      "weekday": {
        "opening_time": "09:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "09:00:00",
        "closing_time": "19:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "The Fix",
    "store_id": "WB-19eb7cb164041a760fe55fcf",
    "market": "UTAH",
    "store": "HARRISVILLE",
    "company": "THE FIX",
    "carrier": "REPAIR SHOP",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "18:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "The Fix",
    "store_id": "WB-8a8b69c953dd842faf22e664",
    "market": "UTAH",
    "store": "RIVERDALE",
    "company": "THE FIX",
    "carrier": "REPAIR SHOP",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "18:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "The Fix",
    "store_id": "WB-2e007663729886bbb54cd4ba",
    "market": "UTAH",
    "store": "LAYTON",
    "company": "THE FIX",
    "carrier": "REPAIR SHOP",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "18:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "The Fix",
    "store_id": "WB-d124d4044ff293446a2035c8",
    "market": "CHICAGO",
    "store": "PRIME",
    "company": "THE FIX",
    "carrier": "REPAIR SHOP",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "18:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "ARBF",
    "store_id": "WB-4cf8ebe635f5c58dabb8aa0b",
    "market": "TOTAL",
    "store": "EULESS",
    "company": "ARBF",
    "carrier": "TOTAL WIRELESS",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "ARBF",
    "store_id": "WB-fec26ab16331327ba8a541eb",
    "market": "TOTAL",
    "store": "JACKSBORO",
    "company": "ARBF",
    "carrier": "TOTAL WIRELESS",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "ARBF",
    "store_id": "WB-e9becadaf36b612680a59f3d",
    "market": "TOTAL",
    "store": "GANNAN",
    "company": "ARBF",
    "carrier": "TOTAL WIRELESS",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "09:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "09:00:00",
        "closing_time": "19:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "ARBF",
    "store_id": "WB-85c11b5be6174f9a60e1c61c",
    "market": "TOTAL",
    "store": "BENBROOK",
    "company": "ARBF",
    "carrier": "TOTAL WIRELESS",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "17:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-DAL46",
    "market": "DALLAS",
    "store": "824 E BELT LINE RD",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "19:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-DAL47",
    "market": "DALLAS",
    "store": "3007 CARRIER PKWY",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "19:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-DAL54",
    "market": "DALLAS",
    "store": "3250 W. PLEASANT RUN RD",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "19:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-DAL56",
    "market": "DALLAS",
    "store": "1512 S BELT LINE RD",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "19:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-DAL55",
    "market": "DALLAS",
    "store": "1450 W PLEASANT RUN RD",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "19:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-HOU027",
    "market": "HOUSTON",
    "store": "2717 61ST ST",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-HOU025",
    "market": "HOUSTON",
    "store": "803 E NASA PARKWAY SUITE 130",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-HOU026",
    "market": "HOUSTON",
    "store": "1805 GARTH RD STE 1805",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-HOU028",
    "market": "HOUSTON",
    "store": "5102 BROADWAY ST STE G",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-HOU029",
    "market": "HOUSTON",
    "store": "7058 BISSONNET ST",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-HOU035",
    "market": "HOUSTON",
    "store": "6911 MARTIN LUTHER KING BLVD",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "19:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-HOU036",
    "market": "HOUSTON",
    "store": "5104 HARRISBURG BLVD STE 300",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-REN01",
    "market": "RENO",
    "store": "1940 E WILLIAM",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-REN02",
    "market": "RENO",
    "store": "4385 NEIL RD",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-REN03",
    "market": "RENO",
    "store": "421 KEYSTONE AVE",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-REN04",
    "market": "RENO",
    "store": "667 N MCCARRAN BLVD",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-REN06",
    "market": "RENO",
    "store": "2900 CLEAR ACRE LN",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Connect",
    "store_id": "NTG-REN05",
    "market": "RENO",
    "store": "1901 SILVERADA BLVD 2C",
    "company": "CONNECT WIRELESS",
    "carrier": "METRO BY T-MOBILE",
    "source_id": "connect",
    "schedules": {
      "weekday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "saturday": {
        "opening_time": "10:00:00",
        "closing_time": "20:00:00"
      },
      "sunday": {
        "opening_time": "12:00:00",
        "closing_time": "18:00:00"
      }
    }
  },
  {
    "dealer": "Smoke Magic",
    "store_id": "WB-279898cbdcc77fd6471194f6",
    "market": "DALLAS",
    "store": "MAGIC 1",
    "company": "SMOKE MAGIC",
    "carrier": "SMOKE SHOP",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "09:00:00",
        "closing_time": "23:00:00"
      },
      "saturday": {
        "opening_time": "09:00:00",
        "closing_time": "23:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "20:00:00"
      }
    }
  },
  {
    "dealer": "Smoke Magic",
    "store_id": "WB-d3b54e24cc0c91ec50a25fef",
    "market": "DALLAS",
    "store": "MAGIC 2",
    "company": "SMOKE MAGIC",
    "carrier": "SMOKE SHOP",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "09:00:00",
        "closing_time": "22:00:00"
      },
      "saturday": {
        "opening_time": "09:00:00",
        "closing_time": "00:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "22:00:00"
      }
    }
  },
  {
    "dealer": "Smoke Magic",
    "store_id": "WB-33fc6b91f54dd55dd1e9d0ed",
    "market": "DALLAS",
    "store": "MAGIC 3",
    "company": "SMOKE MAGIC",
    "carrier": "SMOKE SHOP",
    "source_id": null,
    "schedules": {
      "weekday": {
        "opening_time": "09:00:00",
        "closing_time": "22:00:00"
      },
      "saturday": {
        "opening_time": "09:00:00",
        "closing_time": "00:00:00"
      },
      "sunday": {
        "opening_time": "11:00:00",
        "closing_time": "22:00:00"
      }
    }
  }
]
$schedules$::jsonb) as x(dealer text,store_id text,market text,store text,company text,carrier text,source_id text,schedules jsonb);
