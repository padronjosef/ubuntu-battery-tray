import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// Status area keys created by the AppIndicator extension end with the item object path.
const ITEM_PATH = '/org/ayatana/NotificationItem/battery_tray_';
// Left to right order in the top bar.
const ORDER = ['keyboard', 'headset', 'mouse'];
// battery_tray/app.py appends one of these suffixes to the indicator title.
const LEVELS = [
    {suffix: ' (charging)', name: 'charging', styleClass: 'battery-tray-charging'},
    {suffix: ' (critical)', name: 'critical', styleClass: 'battery-tray-low', blinkEveryMinutes: 1},
    {suffix: ' (low)', name: 'low', styleClass: 'battery-tray-low', blinkEveryMinutes: 10},
];
const STYLE_CLASSES = [...new Set(LEVELS.map(level => level.styleClass))];
const BREATHS = 2;
const BREATH_HALF_MS = 700; // fade out, then fade back in
const BREATH_MIN_OPACITY = 40;

export default class BatteryTrayLeftExtension extends Extension {
    enable() {
        this._watched = new Map();
        this._levels = new Map();
        this._minute = 0;
        this._tickId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 60, () => {
            this._minute++;
            for (const [statusIcon, level] of this._levels) {
                if (level.blinkEveryMinutes && this._minute % level.blinkEveryMinutes === 0)
                    this._blink(statusIcon);
            }
            return GLib.SOURCE_CONTINUE;
        });
        this._handlerId = Main.panel._rightBox.connect('child-added', () => this._scheduleMove());
        this._scheduleMove();
    }

    disable() {
        Main.panel._rightBox.disconnect(this._handlerId);
        this._handlerId = null;
        if (this._idleId) {
            GLib.source_remove(this._idleId);
            this._idleId = null;
        }
        GLib.source_remove(this._tickId);
        this._tickId = null;
        for (const [statusIcon, ids] of this._watched) {
            ids.forEach(([source, id]) => source.disconnect(id));
            STYLE_CLASSES.forEach(styleClass => statusIcon.remove_style_class_name(styleClass));
            statusIcon._label?.remove_all_transitions();
            if (statusIcon._label)
                statusIcon._label.opacity = 255;
        }
        this._watched = null;
        this._levels = null;
        for (const {statusIcon} of this._batteryIndicators())
            this._reparent(statusIcon.container, Main.panel._rightBox, 0);
    }

    _scheduleMove() {
        if (this._idleId)
            return;
        // addToStatusArea registers the key and adds the actor in one go; move once it settles.
        this._idleId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._idleId = null;
            this._moveLeft();
            return GLib.SOURCE_REMOVE;
        });
    }

    _moveLeft() {
        const leftBox = Main.panel._leftBox;
        for (const {statusIcon} of this._batteryIndicators()) {
            this._reparent(statusIcon.container, leftBox, leftBox.get_n_children());
            this._watchLevel(statusIcon);
        }
    }

    _watchLevel(statusIcon) {
        const indicator = statusIcon._indicator;
        if (this._watched.has(statusIcon) || !indicator)
            return;
        const update = () => {
            const title = indicator.title ?? '';
            const level = LEVELS.find(candidate => title.endsWith(candidate.suffix));
            const previous = this._levels.get(statusIcon);
            STYLE_CLASSES.forEach(styleClass => {
                if (styleClass === level?.styleClass)
                    statusIcon.add_style_class_name(styleClass);
                else
                    statusIcon.remove_style_class_name(styleClass);
            });
            if (level)
                this._levels.set(statusIcon, level);
            else
                this._levels.delete(statusIcon);
            // Blink right away when a device first drops to a lower level.
            if (level?.blinkEveryMinutes && level.name !== previous?.name)
                this._blink(statusIcon);
        };
        const ids = [
            [indicator, indicator.connect('accessible-name', update)],
            [statusIcon, statusIcon.connect('destroy', () => {
                this._watched?.delete(statusIcon);
                this._levels?.delete(statusIcon);
            })],
        ];
        this._watched.set(statusIcon, ids);
        update();
    }

    // Only the percentage text breathes (fades out and back in); the AppIndicator
    // extension keeps it in `_label`.
    _blink(statusIcon) {
        const label = statusIcon._label;
        if (!label)
            return;
        label.remove_all_transitions();
        let remaining = BREATHS * 2;
        const next = () => {
            if (remaining-- === 0 || !this._watched?.has(statusIcon)) {
                label.opacity = 255;
                return;
            }
            label.ease({
                opacity: remaining % 2 === 1 ? BREATH_MIN_OPACITY : 255,
                duration: BREATH_HALF_MS,
                mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
                onComplete: next,
            });
        };
        next();
    }

    _batteryIndicators() {
        return Object.entries(Main.panel.statusArea)
            .filter(([key, statusIcon]) => statusIcon && key.includes(ITEM_PATH))
            .map(([key, statusIcon]) => ({
                rank: ORDER.indexOf(key.slice(key.indexOf(ITEM_PATH) + ITEM_PATH.length)),
                statusIcon,
            }))
            .sort((a, b) => a.rank - b.rank);
    }

    _reparent(actor, box, index) {
        const parent = actor.get_parent();
        if (parent === box)
            box.set_child_at_index(actor, Math.min(index, box.get_n_children() - 1));
        else {
            parent?.remove_child(actor);
            box.insert_child_at_index(actor, index);
        }
    }
}
