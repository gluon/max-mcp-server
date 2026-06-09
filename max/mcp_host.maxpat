{
	"patcher": {
		"fileversion": 1,
		"appversion": {
			"major": 8,
			"minor": 6,
			"revision": 0,
			"architecture": "x64",
			"modernui": 1
		},
		"classnamespace": "box",
		"rect": [
			80.0,
			80.0,
			1060.0,
			600.0
		],
		"default_fontsize": 12.0,
		"default_fontface": 0,
		"default_fontname": "Arial",
		"gridonopen": 1,
		"gridsize": [
			15.0,
			15.0
		],
		"gridsnaponopen": 1,
		"objectsnaponopen": 1,
		"statusbarvisible": 2,
		"toolbarvisible": 1,
		"boxes": [
			{
				"box": {
					"id": "obj-1",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						40.0,
						40.0,
						110.0,
						22.0
					],
					"text": "udpreceive 7400",
					"outlettype": [
						"anything"
					],
					"varname": "mcp_udpr"
				}
			},
			{
				"box": {
					"id": "obj-2",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 9,
					"patching_rect": [
						40.0,
						90.0,
						520.0,
						22.0
					],
					"text": "route /newdefault /connect /disconnect /delete /dsp /send /dump /setbox",
					"outlettype": [
						"",
						"",
						"",
						"",
						"",
						"",
						"",
						"",
						""
					],
					"varname": "mcp_route"
				}
			},
			{
				"box": {
					"id": "obj-3",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						40.0,
						150.0,
						170.0,
						22.0
					],
					"text": "prepend script newdefault",
					"outlettype": [
						""
					],
					"varname": "mcp_pnew"
				}
			},
			{
				"box": {
					"id": "obj-4",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						220.0,
						150.0,
						150.0,
						22.0
					],
					"text": "prepend script connect",
					"outlettype": [
						""
					],
					"varname": "mcp_pcon"
				}
			},
			{
				"box": {
					"id": "obj-5",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						380.0,
						150.0,
						160.0,
						22.0
					],
					"text": "prepend script disconnect",
					"outlettype": [
						""
					],
					"varname": "mcp_pdis"
				}
			},
			{
				"box": {
					"id": "obj-6",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						550.0,
						150.0,
						140.0,
						22.0
					],
					"text": "prepend script delete",
					"outlettype": [
						""
					],
					"varname": "mcp_pdel"
				}
			},
			{
				"box": {
					"id": "obj-15",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						700.0,
						150.0,
						150.0,
						22.0
					],
					"text": "prepend script send",
					"outlettype": [
						""
					],
					"varname": "mcp_psend"
				}
			},
			{
				"box": {
					"id": "obj-7",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 3,
					"patching_rect": [
						300.0,
						210.0,
						60.0,
						22.0
					],
					"text": "sel 1 0",
					"outlettype": [
						"bang",
						"bang",
						""
					],
					"varname": "mcp_sel"
				}
			},
			{
				"box": {
					"id": "obj-8",
					"maxclass": "message",
					"numinlets": 2,
					"numoutlets": 1,
					"patching_rect": [
						300.0,
						260.0,
						90.0,
						22.0
					],
					"text": "; dsp start",
					"outlettype": [
						""
					],
					"varname": "mcp_dspon"
				}
			},
			{
				"box": {
					"id": "obj-9",
					"maxclass": "message",
					"numinlets": 2,
					"numoutlets": 1,
					"patching_rect": [
						400.0,
						260.0,
						90.0,
						22.0
					],
					"text": "; dsp stop",
					"outlettype": [
						""
					],
					"varname": "mcp_dspoff"
				}
			},
			{
				"box": {
					"id": "obj-10",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 0,
					"patching_rect": [
						560.0,
						210.0,
						120.0,
						22.0
					],
					"text": "print void_send",
					"varname": "mcp_print"
				}
			},
			{
				"box": {
					"id": "obj-11",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						40.0,
						320.0,
						90.0,
						22.0
					],
					"text": "thispatcher",
					"outlettype": [
						""
					],
					"varname": "mcp_thisp"
				}
			},
			{
				"box": {
					"id": "obj-12",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 1,
					"patching_rect": [
						860.0,
						90.0,
						100.0,
						22.0
					],
					"text": "v8 dump.js",
					"outlettype": [
						""
					],
					"varname": "mcp_dump"
				}
			},
			{
				"box": {
					"id": "obj-13",
					"maxclass": "newobj",
					"numinlets": 1,
					"numoutlets": 0,
					"patching_rect": [
						860.0,
						150.0,
						160.0,
						22.0
					],
					"text": "udpsend 127.0.0.1 7401",
					"varname": "mcp_udps"
				}
			},
			{
				"box": {
					"id": "obj-14",
					"maxclass": "comment",
					"numinlets": 1,
					"numoutlets": 0,
					"patching_rect": [
						40.0,
						360.0,
						900.0,
						40.0
					],
					"text": "maxmsp-mcp host (v0.2.1). Keep open. Machinery is varname mcp_* (filtered from dumps). /dump -> [v8 dump.js] reads boxtext + patchcords. /setbox sets message content. /send is a print stub.",
					"varname": "mcp_note"
				}
			}
		],
		"lines": [
			{
				"patchline": {
					"source": [
						"obj-1",
						0
					],
					"destination": [
						"obj-2",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						0
					],
					"destination": [
						"obj-3",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						1
					],
					"destination": [
						"obj-4",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						2
					],
					"destination": [
						"obj-5",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						3
					],
					"destination": [
						"obj-6",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						4
					],
					"destination": [
						"obj-7",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						5
					],
					"destination": [
						"obj-10",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						6
					],
					"destination": [
						"obj-12",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-2",
						7
					],
					"destination": [
						"obj-15",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-3",
						0
					],
					"destination": [
						"obj-11",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-4",
						0
					],
					"destination": [
						"obj-11",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-5",
						0
					],
					"destination": [
						"obj-11",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-6",
						0
					],
					"destination": [
						"obj-11",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-15",
						0
					],
					"destination": [
						"obj-11",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-7",
						0
					],
					"destination": [
						"obj-8",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-7",
						1
					],
					"destination": [
						"obj-9",
						0
					]
				}
			},
			{
				"patchline": {
					"source": [
						"obj-12",
						0
					],
					"destination": [
						"obj-13",
						0
					]
				}
			}
		]
	}
}